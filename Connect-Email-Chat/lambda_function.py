import os
import boto3
import requests
import sys
from email import policy
from email.parser import BytesParser
from urllib.parse import unquote
from botocore.exceptions import ClientError


SNS_TOPIC = os.environ['SNS_TOPIC']
CONTACT_FLOW_ID = os.environ['CONTACT_FLOW_ID']
INSTANCE_ID = os.environ['INSTANCE_ID']

participant_client = boto3.client('connectparticipant')
connect_client = boto3.client('connect')


def lambda_handler(event, context):
    print(event)
    s3 = boto3.client('s3')

    for rec in event['Records']:
        fileKey = unquote(unquote(rec['s3']['object']['key']))
        bucket = rec['s3']['bucket']['name']

        obj = s3.get_object(Bucket=bucket, Key=fileKey)
        raw_mail = obj['Body'].read()
        
        msg = BytesParser(policy=policy.default).parsebytes(raw_mail)
        msgFrom = strip_address((msg.get('From')))
        msgSubject=msg.get('Subject')

        
        msgBody=""
        files = []
        if msg.is_multipart():
            for part in msg.walk():
                
                ctype = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition'))
                fileAttached = {}
                if content_disposition and 'attachment' in content_disposition:
                    fileAttached['name'] = part.get_filename()
                    fileAttached['type'] = part.get_content_type()
                    fileAttached['data'] = part.get_content()
                    fileAttached['size'] = sys.getsizeof(fileAttached['data']) - 33 ## Removing BYTES overhead
                    
                    files.append(fileAttached)
                    
                
                elif ctype == 'text/plain':
                    try:
                        body = part.get_payload(decode=True)
                        msgBody += body.decode()
                        
                    except Exception as err:
                        print(err)
                        print("Attempting decoding as latin1")
                        body = part.get_payload(decode=True).decode('latin1')
                        msgBody += body
                    
        # not multipart 
        else:
            print("Not multipart")
            try:
                body = part.get_payload(decode=True)
                msgBody += body.decode()
                
            except Exception as err:
                print(err)
                print("Attempting decoding as latin1")
                body = part.get_payload(decode=True).decode('latin1')
                msgBody += body
            

        start_chat_response = start_chat(msgSubject, msgFrom, msgBody, 'email',CONTACT_FLOW_ID,INSTANCE_ID)
        start_stream_response = start_stream(INSTANCE_ID, start_chat_response['ContactId'], SNS_TOPIC)
        create_connection_response = create_connection(start_chat_response['ParticipantToken'])
        ##send_message_response = send_message(msgBody, msgFrom, create_connection_response['ConnectionCredentials']['ConnectionToken'])
        if(len(files)>0):
            for file in files:
                attachmentResponse = attach_file(file['data'],file['name'],file['size'],file['type'],create_connection_response['ConnectionCredentials']['ConnectionToken'])
        
        
def strip_address(address):
    # Extract address
    idx1 = address.find('<')
    idx2 = address.find('>')

    if idx1 > 0 and idx2 > 0:
        return address[idx1 + 1: idx2]
    else:
        return address

def start_chat(msgSubject,msgFrom, msgBody, channel,contactFlow,connectID):

    start_chat_response = connect_client.start_chat_contact(
            InstanceId=connectID,
            ContactFlowId=contactFlow,
            Attributes={
                'Channel': channel,
                'From':msgFrom,
                'Body':msgBody,
                'Subject': msgSubject
            },
            ParticipantDetails={
                'DisplayName': msgFrom
            },
            InitialMessage={
                'ContentType': 'text/plain',
                'Content': msgSubject
            },
            ##SupportedMessagingContentTypes= [ "text/plain", "text/markdown", "application/vnd.amazonaws.connect.message.interactive.response"]
            )
    return start_chat_response

def start_stream(connectID, ContactId, topicARN):
    
    start_stream_response = connect_client.start_contact_streaming(
        InstanceId=connectID,
        ContactId=ContactId,
        ChatStreamingConfiguration={
            'StreamingEndpointArn': topicARN
            }
        )
    return start_stream_response

def create_connection(ParticipantToken):
    
    create_connection_response = participant_client.create_participant_connection(
        Type=['CONNECTION_CREDENTIALS'],
        ParticipantToken=ParticipantToken,
        ConnectParticipant=True
        )
    return(create_connection_response)

def send_message(message, name,connectionToken):
    print("Sending msg")
    try:
        response = participant_client.send_message(
        ContentType='text/plain', ##text/plain and text/markdown
        Content= message,
        ConnectionToken= connectionToken
        )
    except ClientError as e:
        print("Error when sending message")
        print(e)
        return False
        
    return response


def upload_data_to_s3(bytes_data,bucket_name, s3_key):
    s3_resource = boto3.resource('s3')
    obj = s3_resource.Object(bucket_name, s3_key)
    obj.put(ACL='private', Body=bytes_data)

    s3_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
    return s3_url


def attach_file(fileData,fileName,fileSize,fileType,ConnectionToken):
    
    try:
        attachResponse = participant_client.start_attachment_upload(
        ContentType=fileType,
        AttachmentSizeInBytes=fileSize,
        AttachmentName=fileName,
        ConnectionToken=ConnectionToken
        )
    except ClientError as e:
        print("Error while creating attachment")
        if(e.response['Error']['Code'] =='AccessDeniedException'):
            print(e.response['Error'])
            raise e
        elif(e.response['Error']['Code'] =='ValidationException'):
            print(e.response['Error'])
            return None
    else:
        try:
            filePostingResponse = requests.put(attachResponse['UploadMetadata']['Url'], 
            data=fileData,
            headers=attachResponse['UploadMetadata']['HeadersToInclude'])
        except ClientError as e:
            print("Error while uploading")
            print(e.response['Error'])
            raise e
        else:
            print(filePostingResponse.status_code) 
            verificationResponse = participant_client.complete_attachment_upload(
                AttachmentIds=[attachResponse['AttachmentId']],
                ConnectionToken=ConnectionToken)
            print("Verification Response")
            print(verificationResponse)
            return attachResponse['AttachmentId']
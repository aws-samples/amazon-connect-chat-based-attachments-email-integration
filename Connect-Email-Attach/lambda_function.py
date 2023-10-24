## Map Attachment files to Connect Contact.
import json
import boto3
import os


from botocore.exceptions import ClientError

INSTANCE_ID=os.environ['INSTANCE_ID']

def lambda_handler(event, context):
    print(event)
    for record in event['Records']:
        message = json.loads(record['Sns']['Message'])
        message_type= message['Type']
        
        if(message_type == 'ATTACHMENT' and message['ParticipantRole'] != 'CUSTOMER'):
            contactId = message['ContactId']
            print("contactId")
            print(contactId)
            attachments=[]
            for attachedFile in message['Attachments']:
                attachment={}
                attachment['attachmentId'] = attachedFile['AttachmentId']
                attachment['attachmentName'] = attachedFile['AttachmentName']
                attachment['contentType'] = attachedFile['ContentType']
                attachment['fileLocation'] = get_file_location(attachedFile,contactId,message['AbsoluteTime'])
                attachments.append(attachment)
            set_contact_attributes(contactId,INSTANCE_ID, {'attachments':json.dumps(attachments)})
        

    response = {
                "statusCode": 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                    },
                "body": "",
            }
        
    return response

def get_file_location(attachedFile,contactId,absTime):
    
    ##Get file prefix: YYYY/MM/DD
    filePrefix = absTime.split('T',1)[0].replace('-','/')
    
    ##Get file name: contactId_attachmentId_YYYMMDDTHH:MM_UTC.fileExt
    fileLocation = contactId +'_'+ attachedFile['AttachmentId']+'_'+absTime.rpartition(":")[0].replace('-','')+'_UTC.'+attachedFile['AttachmentName'].split('.')[-1]
    return filePrefix+'/'+fileLocation

def set_contact_attributes(contactId,instanceId, attributes):
    connect_client = boto3.client('connect')

    try:
        response = connect_client.update_contact_attributes(
        InitialContactId=contactId,
        InstanceId=instanceId,
        Attributes={
            **attributes
            }
        )
    except ClientError as e:
        print("Error setting attribute")
        print(e)
        return False
    
    else:
        print(response)
        return response
# Reply to email using SES
import json
import boto3
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
from botocore.exceptions import ClientError


SOURCE_EMAIL = os.environ['SOURCE_EMAIL']
BUCKET = os.environ['BUCKET']
CONNECT_ATTACHMENTS_LOCATION = os.environ['CONNECT_ATTACHMENTS_LOCATION']

ses = boto3.client("ses")
s3 = boto3.client("s3")
connect_client = boto3.client('connect')

def lambda_handler(event, context):
    print(event)
    if event['Details']['ContactData']['RelatedContactId']:
        contactId = event['Details']['ContactData']['RelatedContactId']
    else:
        contactId = event['Details']['ContactData']['InitialContactId']
    instanceId=event['Details']['ContactData']['InstanceARN'].split('/')[-1]
    
    attachments_list = get_attachments_list(contactId,instanceId)
    print("attachments")
    print(attachments_list)
    
    subject = "Re:" + str(event['Details']['ContactData']['Attributes']['Subject'])
    content = str(event['Details']['Parameters']['msgResponse']) + '\n ==== \n' + str(event['Details']['ContactData']['Attributes']['Body'])
    
    ccAddress = str(event['Details']['ContactData']['Attributes'].get('ccAddress',''))
    
    destination = [str(event['Details']['ContactData']['Attributes']['From'])]
    print(ccAddress)
    if ccAddress:
        destination.append(list(map(str.strip, ccAddress.split(','))))

    signature = str(event['Details']['ContactData']['Attributes'].get('signature',None))
    
    if(attachments_list):
        send_email(destination,subject, content, json.loads(attachments_list),signature)
    else:
        send_email(destination,subject, content, False,signature)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Message sent!')
    }

def get_attachments_list(contactId,instanceId):
    
    attributes = connect_client.get_contact_attributes(
    InstanceId=instanceId,
    InitialContactId=contactId
    )
    
    if 'attachments' in attributes['Attributes'] and attributes['Attributes']['attachments']:
        print("Found attachments")
        return attributes['Attributes']['attachments']
    else:
        return False

def send_email(destination,subject, content, files,signature):

    CHARSET = "utf-8"
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = SOURCE_EMAIL 
    msg['To'] = destination[0]
    
    msg_body = MIMEMultipart('alternative')

    textpart = MIMEText(content.encode(CHARSET), 'plain', CHARSET)
    msg_body.attach(textpart)
    msg.attach(msg_body)
    BODY_HTML= '<html><head></head><body><p><h1>Previo</h1>'+content+'<img src="cid:firma">'+'</p></body></html>'
    htmlpart = MIMEText(BODY_HTML.encode(CHARSET), 'html', CHARSET)
    msg_body.attach(htmlpart)

    if(signature):
        ## Add Signature
        signatureFile = 'firmaSven.gif'
        s3.download_file(BUCKET, CONNECT_ATTACHMENTS_LOCATION + '/' + signatureFile, '/tmp/' +signatureFile)
        msgImage = MIMEImage(open('/tmp/' + signatureFile, 'rb').read())
        msgImage.add_header('Content-ID', '<firma>') ##Add ID to image
        msg_body.attach(msgImage)


    if (files and len(files)>0):
        print(files)
        for file in files:
            print("Getting file")
            print(CONNECT_ATTACHMENTS_LOCATION + '/' + file['fileLocation'])
            s3.download_file(BUCKET, CONNECT_ATTACHMENTS_LOCATION + '/' + file['fileLocation'], '/tmp/' +file['attachmentName'])
            att = MIMEApplication(open('/tmp/' +file['attachmentName'], 'rb').read())
            att.add_header('Content-Disposition','attachment',filename=os.path.basename('/tmp/' +file['attachmentName']))
            msg.attach(att)

    try:
        response = ses.send_raw_email(
            Source=SOURCE_EMAIL,
            Destinations=
                destination
            ,
            RawMessage={
                'Data':msg.as_string(),
            },
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])


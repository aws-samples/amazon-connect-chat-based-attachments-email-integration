# Reply to email using SES
import json
import boto3
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
    contactId = event['Details']['ContactData']['RelatedContactId']
    instanceId=event['Details']['ContactData']['InstanceARN'].split('/')[-1]
    
    attachments_list = get_attachments_list(contactId,instanceId)
    print("attachments")
    print(attachments_list)
    destination = str(event['Details']['ContactData']['Attributes']['From'])
    subject = "Re:" + str(event['Details']['ContactData']['Attributes']['Subject'])
    content = str(event['Details']['Parameters']['msgResponse']) + '\n ==== \n' + str(event['Details']['ContactData']['Attributes']['Body'])
    
    if(attachments_list):
        send_attachments(destination,SOURCE_EMAIL,subject, content, json.loads(attachments_list))
    else:
        send_attachments(destination,SOURCE_EMAIL,subject, content, False)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Message sent!')
    }

def send_email(destination,source,subject, content):
    ses_client = boto3.client("ses")
    CHARSET = "UTF-8"
    response = ses_client.send_email(
        Destination={
            "ToAddresses": [
                destination,
            ],
        },
        Message={
            "Body": {
                "Text": {
                    "Charset": CHARSET,
                    "Data": content,
                }
            },
            "Subject": {
                "Charset": CHARSET,
                "Data": subject,
            },
        },
        Source=source
    )



def get_attachments_list(contactId,instanceId):
    
    contactAttributes = {}
    
    attributes = connect_client.get_contact_attributes(
    InstanceId=instanceId,
    InitialContactId=contactId
    )
    
    if 'attachments' in attributes['Attributes'] and attributes['Attributes']['attachments']:
        print("Found attachments")
        return attributes['Attributes']['attachments']
    else:
        return False

def send_attachments(destination,source,subject, content, files):

    CHARSET = "utf-8"
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject 
    msg['From'] = source 
    msg['To'] = destination
    msg_body = MIMEMultipart('alternative')

    textpart = MIMEText(content.encode(CHARSET), 'plain', CHARSET)
    msg_body.attach(textpart)
    msg.attach(msg_body)
    ##htmlpart = MIMEText(BODY_HTML.encode(CHARSET), 'html', CHARSET)
    ##msg_body.attach(htmlpart)



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
            Source=source,
            Destinations=[
                destination
            ],
            RawMessage={
                'Data':msg.as_string(),
            },
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])


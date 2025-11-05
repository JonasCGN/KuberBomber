import json
import boto3
import cfnresponse
import os

s3 = boto3.client('s3')

def lambda_handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))
    bucket_name = event['ResourceProperties']['BucketName']
    directory_path = event['ResourceProperties']['DirectoryPath']  # Local path in Lambda

    try:
        # Only handle "Create" events
        if event['RequestType'] == 'Create':
            print(f"Uploading files from {directory_path} to bucket: {bucket_name}")
            upload_directory(directory_path, bucket_name)

        # Signal success to CloudFormation
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {"Message": "Files uploaded successfully"})

    except Exception as e:
        print(f"Error during file upload: {str(e)}")
        # Signal failure to CloudFormation
        cfnresponse.send(event, context, cfnresponse.FAILED, {"Message": str(e)})

def upload_directory(directory, bucket_name):
    """
    Recursively uploads files from a specified local directory to an S3 bucket.
    """
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            s3_key = os.path.relpath(file_path, directory)
            try:
                s3.upload_file(file_path, bucket_name, s3_key)
                print(f"Uploaded {file_path} to s3://{bucket_name}/{s3_key}")
            except Exception as e:
                print(f"Failed to upload {file_path} due to {str(e)}")

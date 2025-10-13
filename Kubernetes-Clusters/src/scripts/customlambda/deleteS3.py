import json
import boto3
import cfnresponse
import time

s3 = boto3.client('s3')

def lambda_handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))
    bucket_name = event['ResourceProperties']['BucketName']

    try:
        if event['RequestType'] == 'Delete':
            print(f"Deleting objects from bucket: {bucket_name}")
            time.sleep(120)  # Sleep for 120 seconds (2 minutes)

            # Continuously delete all objects in the bucket
            while True:
                objects = s3.list_objects_v2(Bucket=bucket_name)

                if 'Contents' in objects:
                    # Delete all objects in the current batch
                    delete_params = {
                        'Bucket': bucket_name,
                        'Delete': {'Objects': [{'Key': obj['Key']} for obj in objects['Contents']]}
                    }
                    s3.delete_objects(**delete_params)
                    print(f"Deleted {len(objects['Contents'])} objects from bucket: {bucket_name}")

                    # If more objects remain, continue the loop
                    if objects['IsTruncated']:
                        continue
                else:
                    print(f"No objects to delete in bucket: {bucket_name}")
                break

        # Signal success to CloudFormation
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {"Message": "Bucket cleanup complete"})

    except Exception as e:
        print(f"Error during S3 cleanup: {str(e)}")
        # Signal failure to CloudFormation
        cfnresponse.send(event, context, cfnresponse.FAILED, {"Message": str(e)})
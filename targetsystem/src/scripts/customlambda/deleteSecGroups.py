import json
import boto3
import cfnresponse
import time

ec2 = boto3.client('ec2')

def lambda_handler(event, context):
    # Print the event for debugging
    print("Received event: " + json.dumps(event, indent=2))

    try:
        if event['RequestType'] == 'Delete':
            # Search for security groups with the specific tag used by EMR
            response = ec2.describe_security_groups(
                Filters=[
                    {'Name': 'tag:for-use-with-amazon-emr-managed-policies', 'Values': ['true']}
                ]
            )

            security_groups = response['SecurityGroups']

            # First loop: Remove dependencies
            for sg in security_groups:
                sg_id = sg['GroupId']
                try:
                    print(f"Checking for dependencies of security group: {sg_id}")

                    # Find security groups that reference this security group
                    referencing_sgs = ec2.describe_security_groups(
                        Filters=[
                            {'Name': 'ip-permission.group-id', 'Values': [sg_id]}
                        ]
                    )

                    # For each security group referencing this one, remove the inbound rule
                    for referencing_sg in referencing_sgs['SecurityGroups']:
                        referencing_sg_id = referencing_sg['GroupId']
                        print(f"Removing reference from security group {referencing_sg_id} to {sg_id}")

                        # Revoke the inbound rule
                        for permission in referencing_sg['IpPermissions']:
                            for user_id_group_pair in permission['UserIdGroupPairs']:
                                if user_id_group_pair['GroupId'] == sg_id:
                                    ec2.revoke_security_group_ingress(
                                        GroupId=referencing_sg_id,
                                        IpPermissions=[permission]
                                    )
                                    print(f"Revoked ingress rule in security group {referencing_sg_id} referencing {sg_id}")

                except Exception as e:
                    print(f"Failed to remove dependencies for security group {sg_id}: {str(e)}")

            # Second loop: Try deleting the security groups, retry until success
            for sg in security_groups:
                sg_id = sg['GroupId']
                while True:
                    try:
                        print(f"Attempting to delete security group: {sg_id}")
                        ec2.delete_security_group(GroupId=sg_id)
                        print(f"Deleted security group: {sg_id}")
                        break  # Exit the loop if deletion is successful
                    except Exception as e:
                        print(f"Failed to delete security group {sg_id}, retrying: {str(e)}")
                        time.sleep(10)  # Wait 10 seconds before retrying

        # Send a success response to CloudFormation
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {"Message": "Security groups deleted"})

    except Exception as e:
        print(f"Error during security group cleanup: {str(e)}")
        cfnresponse.send(event, context, cfnresponse.FAILED, {"Message": str(e)})
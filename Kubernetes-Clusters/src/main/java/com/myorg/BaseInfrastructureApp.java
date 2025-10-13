package com.myorg;

import software.amazon.awscdk.*;

import java.io.IOException;

public class BaseInfrastructureApp {
    public static void main(final String[] args) throws IOException, InterruptedException {
        App app = new App();

        Stack stack =new BaseInfrastructureStack(app, "BaseInfrastructureStack", StackProps.builder()

                .synthesizer(DefaultStackSynthesizer.Builder.create()
                        .fileAssetsBucketName("cdk-${Qualifier}-assets-${AWS::AccountId}-${AWS::Region}")
                        .bucketPrefix("")

                        // Name of the ECR repository for Docker image assets
                        .imageAssetsRepositoryName("cdk-${Qualifier}-container-assets-${AWS::AccountId}-${AWS::Region}")
                        .dockerTagPrefix("")
                            // ARN of the role assumed by the CLI and Pipeline to deploy here
                        .deployRoleArn("arn:${AWS::Partition}:iam::${AWS::AccountId}:role/LabRole")
                        .deployRoleExternalId("")

                        // ARN of the role used for file asset publishing (assumed from the CLI role)
                        .fileAssetPublishingRoleArn("arn:${AWS::Partition}:iam::${AWS::AccountId}:role/LabRole")
                        .fileAssetPublishingExternalId("")

                        // ARN of the role used for Docker asset publishing (assumed from the CLI role)
                        .imageAssetPublishingRoleArn("arn:${AWS::Partition}:iam::${AWS::AccountId}:role/LabRole")
                        .imageAssetPublishingExternalId("")

                        // ARN of the role passed to CloudFormation to execute the deployments
                        .cloudFormationExecutionRole("arn:${AWS::Partition}:iam::${AWS::AccountId}:role/LabRole")
//                        .cloudFormationExecutionRole("arn:${AWS::Partition}:iam::${AWS::AccountId}:role/EMR_EC2_DefaultRole")

                        .lookupRoleArn("arn:${AWS::Partition}:iam::${AWS::AccountId}:role/LabRole")
                        .lookupRoleExternalId("")

                        // Name of the SSM parameter which describes the bootstrap stack version number
//                        .bootstrapStackVersionSsmParameter("/cdk-bootstrap/${Qualifier}/version")

                        // Add a rule to every template which verifies the required bootstrap stack version
//                        .generateBootstrapVersionRule(true)
//                        .useLookupRoleForStackOperations(true)
//                        .qualifier("abc")
                        .build())
                .build());


        app.synth();
    }
}


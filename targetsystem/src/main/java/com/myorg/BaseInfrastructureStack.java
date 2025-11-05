package com.myorg;

import com.myorg.util.EnvReader;
import com.myorg.util.Util;
import software.amazon.awscdk.*;
import software.amazon.awscdk.Stack;
import software.amazon.awscdk.services.ec2.*;
import software.amazon.awscdk.services.elasticloadbalancingv2.*;
import software.amazon.awscdk.services.elasticloadbalancingv2.targets.InstanceTarget;
import software.amazon.awscdk.services.emr.CfnCluster;
import software.amazon.awscdk.services.iam.*;
import software.amazon.awscdk.services.lambda.Code;
import software.amazon.awscdk.services.lambda.Function;
import software.amazon.awscdk.services.lambda.Runtime;
import software.amazon.awscdk.services.s3.Bucket;
import software.amazon.awscdk.services.s3.assets.Asset;
import software.amazon.awscdk.services.s3.deployment.BucketDeployment;
import software.amazon.awscdk.services.s3.deployment.Source;
import software.constructs.Construct;

import java.io.IOException;
import java.net.InetAddress;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

public class BaseInfrastructureStack extends Stack {
        public BaseInfrastructureStack(final Construct scope, final String id)
                        throws IOException, InterruptedException {
                this(scope, id, null);
        }

        public BaseInfrastructureStack(final Construct scope, final String id, final StackProps props)
                        throws IOException, InterruptedException {
                super(scope, id, props);

                Util util = new Util();
                Map<String, String> env = EnvReader.loadEnv();

                // set your key ID
                String keyName = "vockey";
                String instanceAMI = "ami-080e1f13689e07408"; // ubuntu 22.04
                InstanceType instanceType = InstanceType.of(InstanceClass.T3, InstanceSize.MEDIUM);
                String region = util.getDefaultRegion();
                String labRoleARN = "arn:aws:iam::" + util.getAccount() + ":role/LabRole";
                String googleDrivePath = env.get("GOOGLE_DRIVE_PATH");
                String googleKeyPath = env.get("GOOGLE_KEY_PATH");
                String vmPemKey = env.get("VM_KEY_PATH");
                String RABBITMQ_HOST = env.get("RABBITMQ_HOST");
                String RABBITMQ_PASS = env.get("RABBITMQ_PASS");
                String RABBITMQ_PORT = env.get("RABBITMQ_PORT");
                int numberOfWorkers = 2;
                // int numberOfClients=0;
                String useHPA = "false";
                String barST = "0.2";
                String fooST = "0.18";

                String keyId = util.getKeyPairId(keyName, region);

                IKeyPair iKeyPair = KeyPair.fromKeyPairName(this, keyId, keyName);

                List<String> availabilityZones = getAvailabilityZones();

                // Create a kubernetes cluster VPC
                Vpc vpc = Vpc.Builder.create(this, "k8s_vpc")
                                .defaultInstanceTenancy(DefaultInstanceTenancy.DEFAULT)
                                .enableDnsSupport(true)
                                .enableDnsHostnames(true)
                                .subnetConfiguration(List.of(
                                                SubnetConfiguration.builder()
                                                                .subnetType(SubnetType.PUBLIC) // Define as public
                                                                .name("k8sPublicSubnet")
                                                                .cidrMask(24) // CIDR for public subnets
                                                                .build()))
                                .restrictDefaultSecurityGroup(false)
                                .build();

                ISecurityGroup securityGroup = SecurityGroup.Builder.create(this, id + "_k8s_sg")
                                .securityGroupName(id)
                                .vpc(vpc)
                                .build();
                securityGroup.addIngressRule(Peer.anyIpv4(), Port.allTraffic());
                securityGroup.addIngressRule(Peer.anyIpv6(), Port.allTraffic());

                String hostname = InetAddress.getLocalHost().getHostName();
                // Create an S3 bucket
                Bucket bucket = createBucket("base-bucket-" + hostname, labRoleARN);

                addS3Asset(bucket, "nodes", labRoleARN);

                // change or create new methods for each type of VMs that you have
                Instance cp = createCP("ControlPlane",
                                vpc,
                                instanceAMI,
                                securityGroup,
                                vpc.getPublicSubnets().get(0),
                                iKeyPair, instanceType,
                                bucket, region,
                                labRoleARN,
                                numberOfWorkers,
                                useHPA,
                                barST,
                                fooST);

                List<Instance> instances = new ArrayList<>();
                for (int i = 0; i < numberOfWorkers; i++) {
                        Instance instance = createWN("WN" + i,
                                        vpc,
                                        instanceAMI,
                                        securityGroup,
                                        vpc.getPublicSubnets().get(0),
                                        iKeyPair,
                                        instanceType,
                                        bucket,
                                        vpc.getPublicSubnets().get(0).getAvailabilityZone(),
                                        region,
                                        labRoleARN);
                        instances.add(instance);
                }

                ApplicationLoadBalancer alb = createLB(vpc, instances);

                //// Create a client VPC only in az2
                // Vpc clientVPC = Vpc.Builder.create(this, "client_vpc")
                // .defaultInstanceTenancy(DefaultInstanceTenancy.DEFAULT)
                // .enableDnsSupport(true)
                // .enableDnsHostnames(true)
                // .availabilityZones(new
                //// ArrayList<>(Collections.singletonList(availabilityZones.get(1))))
                // .subnetConfiguration(List.of(
                // SubnetConfiguration.builder()
                // .subnetType(SubnetType.PUBLIC) // Define as public
                // .name("ClientPublicSubnet")
                // .cidrMask(24) // CIDR for public subnets
                // .build()
                // ))
                // .restrictDefaultSecurityGroup(false)
                // .build();

                // ISecurityGroup ClientsecurityGroup = SecurityGroup.Builder.create(this, id +
                // "_client_sg")
                // .securityGroupName(id+"_client")
                // .vpc(clientVPC)
                // .build();
                // ClientsecurityGroup.addIngressRule(Peer.anyIpv4(), Port.allTraffic());
                // ClientsecurityGroup.addIngressRule(Peer.anyIpv6(), Port.allTraffic());

                // for (int i = 0; i < numberOfClients; i++) {
                // createClient("client"+i,
                // clientVPC,
                // instanceAMI,
                // ClientsecurityGroup,
                // clientVPC.getPublicSubnets().get(0),
                // iKeyPair,
                // instanceType,
                // bucket,clientVPC.getPublicSubnets().get(0).getAvailabilityZone(),
                // region,labRoleARN,
                // alb.getLoadBalancerDnsName(),
                // googleDrivePath,googleKeyPath,
                // vmPemKey,
                // cp.getInstance().getAttrPublicIp(),
                // RABBITMQ_HOST,
                // RABBITMQ_PASS,
                // useHPA,
                // RABBITMQ_PORT);
                // }

        }

        public CfnCluster createAnEMRCluter(Bucket bucket, String roleArn, String ubuntuAMIId, String vpcId,
                        String keyName, ISecurityGroup securityGroup, CfnVPCGatewayAttachment gatewayAttachment,
                        Vpc vpc, CfnRoute cfn, int instances) {

                // String ubuntuAmiId = "ami-025b9fd66d61d093a"; // Replace with your Ubuntu AMI
                // ID

                // Define the master instance group with the custom Ubuntu AMI
                CfnCluster.InstanceGroupConfigProperty masterInstanceGroup = CfnCluster.InstanceGroupConfigProperty
                                .builder()
                                .instanceCount(1)
                                .instanceType("m4.xlarge")
                                .name("Master Instance Group")
                                .market("ON_DEMAND")
                                // .customAmiId(ubuntuAmiId) // Use the custom Ubuntu AMI
                                .build();

                // Define the core instance group with the custom Ubuntu AMI
                CfnCluster.InstanceGroupConfigProperty coreInstanceGroup = CfnCluster.InstanceGroupConfigProperty
                                .builder()
                                .instanceCount(instances - 1)
                                .instanceType("m4.xlarge")
                                .name("Core Instance Group")
                                .market("ON_DEMAND")
                                // .customAmiId(ubuntuAmiId) // Use the custom Ubuntu AMI
                                .build();

                // Define the EMR Cluster
                CfnCluster emrCluster = CfnCluster.Builder.create(this, "MyEmrCluster")
                                .name("MyEmrCluster")
                                .releaseLabel("emr-6.5.0")
                                .applications(Arrays.asList(
                                                CfnCluster.ApplicationProperty.builder().name("Hadoop").build(),
                                                CfnCluster.ApplicationProperty.builder().name("Spark").build()))
                                .instances(CfnCluster.JobFlowInstancesConfigProperty.builder()
                                                .ec2SubnetId(vpcId)
                                                .ec2KeyName(keyName)
                                                .masterInstanceGroup(masterInstanceGroup)
                                                .coreInstanceGroup(coreInstanceGroup)
                                                .additionalMasterSecurityGroups(
                                                                Arrays.asList(securityGroup.getSecurityGroupId()))
                                                .additionalSlaveSecurityGroups(
                                                                Arrays.asList(securityGroup.getSecurityGroupId()))
                                                .build())
                                .jobFlowRole("EMR_EC2_DefaultRole")
                                .serviceRole("EMR_DefaultRole")
                                .logUri("s3://" + bucket.getBucketName() + "/")
                                .visibleToAllUsers(true)
                                .build();

                // Reference the existing IAM role by ARN
                IRole existingRole = Role.fromRoleArn(this, "ExistingLambdaRole5", roleArn);

                Function getInstanceIpsLambda = Function.Builder.create(this, "GetInstanceIpsLambda")
                                .runtime(Runtime.PYTHON_3_8)
                                .code(Code.fromAsset("src/scripts/customlambda"))
                                .handler("printIPs.lambda_handler")
                                .timeout(Duration.seconds(300)) // Setting the Lambda timeout
                                .role(existingRole) // Attach the existing IAM role to the Lambda function
                                .build();

                // Create a custom resource to trigger the Lambda function
                CustomResource customResource = CustomResource.Builder.create(this, "CustomResource")
                                .serviceToken(getInstanceIpsLambda.getFunctionArn())
                                .properties(Collections.singletonMap("ClusterId", emrCluster.getRef())) // Pass
                                                                                                        // ClusterId to
                                                                                                        // Lambda
                                .build();

                // Output the instance details retrieved by the Lambda function
                CfnOutput.Builder.create(this, "InstanceDetails")
                                .value(customResource.getAttString("InstanceDetails"))
                                .description("Instance ID, Name, and Public IPs of the instances in the EMR cluster")
                                .build();

                emrCluster.addDependency(cfn);
                emrCluster.addDependency(gatewayAttachment);

                IRole existingRole2 = Role.fromRoleArn(this, "ExistingLabRole9", roleArn);

                // Create the Lambda function using the external Python file
                Function cleanupLambda = Function.Builder.create(this, "CleanupLambda")
                                .runtime(Runtime.PYTHON_3_9)
                                .handler("deleteSecGroups.lambda_handler") // Specify the file and function name
                                .timeout(Duration.minutes(10))
                                .code(Code.fromAsset("src/scripts/customlambda")) // Specify the path to your code
                                                                                  // directory
                                .role(existingRole2)
                                .build();

                // Create the custom resource
                CustomResource customResource3 = CustomResource.Builder.create(this, "CleanupCustomResource")
                                .serviceToken(cleanupLambda.getFunctionArn())
                                .build();

                // Add dependency to ensure custom resource runs after EMR cluster deletion
                customResource3.getNode().addDependency(vpc);

                return emrCluster;

        }

        public ApplicationLoadBalancer createLB(IVpc vpc, List<Instance> instances) {

                ISecurityGroup HPALBAsecurityGroup = SecurityGroup.Builder.create(this, "hpaloadbalance-sg")
                                .securityGroupName("hpaloadbalance-sg")
                                .vpc(vpc)
                                .build();
                HPALBAsecurityGroup.addIngressRule(Peer.anyIpv4(), Port.HTTP);
                HPALBAsecurityGroup.addEgressRule(Peer.anyIpv4(), Port.tcp(30080));

                // Step 3: Create the Application Load Balancer (ALB)
                ApplicationLoadBalancer alb = ApplicationLoadBalancer.Builder.create(this, "hpaalb")
                                .vpc(vpc)
                                .securityGroup(HPALBAsecurityGroup)
                                .internetFacing(true) // Public-facing ALB
                                .loadBalancerName("hpalb")
                                .build();

                List<InstanceTarget> instanceTargets = new ArrayList<>();

                for (Instance instance : instances) {
                        InstanceTarget instanceTarget = new InstanceTarget(instance, 30080);
                        instanceTargets.add(instanceTarget);
                }

                // Step 4: Create a Target Group for the VMs (pointing to port 30080)
                ApplicationTargetGroup targetGroup = ApplicationTargetGroup.Builder.create(this, "HPATargetGroup")
                                .vpc(vpc)
                                .protocol(ApplicationProtocol.HTTP)
                                .port(30080) // Target VMs' port
                                .healthCheck(HealthCheck.builder()
                                                .path("/test") // Make sure the path matches where your app responds
                                                .port("30080") // Health check port should match the service port
                                                .interval(Duration.seconds(300)) // Health check interval
                                                .timeout(Duration.seconds(5)) // Health check timeout
                                                .unhealthyThresholdCount(2) // Number of consecutive failures to mark as
                                                                            // unhealthy
                                                .healthyThresholdCount(3) // Number of successes to mark as healthy
                                                .healthyHttpCodes("404")
                                                .build())
                                .targetType(TargetType.INSTANCE)
                                .targets(instanceTargets)
                                .build();

                // Step 5: Add a Listener to the ALB (Listening on port 80)
                ApplicationListener listener = ApplicationListener.Builder.create(this, "HPAListener")
                                .loadBalancer(alb)
                                .protocol(ApplicationProtocol.HTTP)
                                .port(80) // ALB will listen on port 80
                                .defaultTargetGroups(List.of(targetGroup)) // Forward traffic to target group
                                .build();

                CfnOutput.Builder.create(this, "LoadBalancerDNS")
                                .value(alb.getLoadBalancerDnsName())
                                .description("The DNS name of the ALB")
                                .exportName("AlbDnsName")
                                .build();

                return alb;
        }

        public Map<PublicSubnet, CfnRoute> createSubnets(int numberOfZones, Vpc vpc,
                        CfnVPCGatewayAttachment cfnVPCGatewayAttachment) {

                List<String> availabilityZones = getAvailabilityZones();

                Map<PublicSubnet, CfnRoute> subnets = new HashMap<>();

                for (int i = 0; i < numberOfZones; i++) {
                        PublicSubnet publicSubnet = new PublicSubnet(this, "publicsubnet_" + i, PublicSubnetProps
                                        .builder()
                                        .availabilityZone(availabilityZones.get(i))
                                        .cidrBlock("10.0." + i + ".0/24")
                                        .vpcId(vpc.getVpcId())
                                        .mapPublicIpOnLaunch(true)
                                        .build());

                        CfnRoute cfnRoute = CfnRoute.Builder.create(this, "base_route_" + i)
                                        .routeTableId(publicSubnet.getRouteTable().getRouteTableId())
                                        .gatewayId(cfnVPCGatewayAttachment.getInternetGatewayId())
                                        .destinationCidrBlock("0.0.0.0/0")
                                        .build();
                        vpc.selectSubnets().getSubnets().add(publicSubnet);

                        cfnRoute.addDependency(cfnVPCGatewayAttachment);

                        subnets.put(publicSubnet, cfnRoute);
                }
                return subnets;
        }

        private Map<PublicSubnet, CfnSubnetRouteTableAssociation> createSubnets(Vpc vpc, String routeTableId) {

                List<String> availabilityZones = getAvailabilityZones();
                Map<PublicSubnet, CfnSubnetRouteTableAssociation> subnets = new HashMap<>();

                for (int i = 0; i < 2; i++) { // Create two subnets
                        PublicSubnet publicSubnet = PublicSubnet.Builder.create(this, "publicsubnet_" + i)
                                        .availabilityZone(availabilityZones.get(i))
                                        .cidrBlock("10.0." + i + ".0/24")
                                        .vpcId(vpc.getVpcId())
                                        .mapPublicIpOnLaunch(true)
                                        .build();

                        // Associate the subnet with the route table
                        CfnSubnetRouteTableAssociation cfn = CfnSubnetRouteTableAssociation.Builder
                                        .create(this, "SubnetRouteTableAssociation_" + i)
                                        .subnetId(publicSubnet.getSubnetId())
                                        .routeTableId(routeTableId)
                                        .build();

                        subnets.put(publicSubnet, cfn);
                }
                return subnets;

        }

        public Instance createCP(String name, Vpc vpc, String instanceAMI, ISecurityGroup securityGroup, ISubnet subnet,
                        IKeyPair iKeyPair, InstanceType instanceType, Bucket bucket, String region,
                        String exitingRoleArn, int numberOfWN, String useHPA, String barST, String fooST)
                        throws IOException {

                String bootstrap = Files.readString(Paths.get("./src/scripts/nodes/controlPlane/bootstrap.sh"),
                                Charset.defaultCharset());

                String userDataString = "echo '" + bootstrap + "' > /home/ubuntu/bootstrap.sh\n" + // add this file
                                "chmod +x /home/ubuntu/bootstrap.sh\n" + // add permission to execute the copied script
                                "/home/ubuntu/bootstrap.sh\n" + // run the script
                                "aws s3 cp --recursive s3://" + bucket.getBucketName()
                                + "/controlPlane/ /home/ubuntu/ \n" + // update
                                "chmod +x /home/ubuntu/*.sh\n" + // add permission to execute the copied script
                                "/home/ubuntu/controlPlaneInstall.sh\n" + // run the script
                                "/home/ubuntu/afterInstall.sh " + bucket.getBucketName() + " " + numberOfWN + " "
                                + useHPA + " " + barST + " " + fooST + "\n"; // run the script

                Instance instance = createEc2Instance(name, vpc, instanceAMI, securityGroup, subnet, iKeyPair,
                                userDataString, instanceType, region, exitingRoleArn);

                // Porta fixa do NodePort (por exemplo, 30080)
                String nodePortGrafana = "30081";

                // URL completa de acesso ao Grafana
                CfnOutput.Builder.create(this, "GrafanaAccessURL" + name)
                                .description("URL de acesso ao Grafana via NodePort da instância " + name)
                                .value("http://" + instance.getInstance().getAttrPublicIp() + ":" + nodePortGrafana)
                                .build();

                return instance;
        }

        public Instance createWN(String name, Vpc vpc, String instanceAMI, ISecurityGroup securityGroup, ISubnet subnet,
                        IKeyPair iKeyPair, InstanceType instanceType, Bucket bucket, String dcNum, String region,
                        String exitingRoleArn) throws IOException {

                String bootstrap = Files.readString(Paths.get("./src/scripts/nodes/workerNode/bootstrap.sh"),
                                Charset.defaultCharset());

                String userDataString = "echo '" + bootstrap + "' > /home/ubuntu/bootstrap.sh\n" + // add this file
                                "chmod +x /home/ubuntu/bootstrap.sh\n" + // add permission to execute the copied script
                                "/home/ubuntu/bootstrap.sh\n" + // run the script
                                "aws s3 cp --recursive s3://" + bucket.getBucketName() + "/workerNode/ /home/ubuntu/ \n"
                                + // update
                                "chmod +x /home/ubuntu/*.sh\n" + // add permission to execute the copied script
                                "/home/ubuntu/workerNodeInstall.sh " + bucket.getBucketName() + "\n"; // run the script

                Instance instance = createEc2Instance(name, vpc, instanceAMI, securityGroup, subnet, iKeyPair,
                                userDataString, instanceType, region, exitingRoleArn);

                Tags.of(instance).add("DC", "" + dcNum);

                return instance;
        }

        public Instance createClient(String name,
                        Vpc vpc,
                        String instanceAMI,
                        ISecurityGroup securityGroup,
                        ISubnet subnet,
                        IKeyPair iKeyPair,
                        InstanceType instanceType,
                        Bucket bucket,
                        String dcNum,
                        String region,
                        String exitingRoleArn,
                        String lbAddr,
                        String googleDrivePath,
                        String googleKeyPath,
                        String vmPemKeys,
                        String IPCP,
                        String rabbitHost,
                        String rabbitPass,
                        String useHPA,
                        String rabbitPort) throws IOException {

                String bootstrap = Files.readString(Paths.get("./src/scripts/nodes/workerNode/bootstrap.sh"),
                                Charset.defaultCharset());

                // if was added a key upload the google key servuce file to VM
                String googleservices = "";
                if (googleKeyPath != null) {
                        googleservices = Files.readString(Paths.get(googleKeyPath), Charset.defaultCharset());
                        googleservices = "echo '" + googleservices + "' > /home/ubuntu/googleservices.json\n";
                }

                String awsacademy = Files.readString(Paths.get(vmPemKeys), Charset.defaultCharset());

                String userDataString = "echo '" + bootstrap + "' > /home/ubuntu/bootstrap.sh\n" + // add this file
                                "chmod +x /home/ubuntu/bootstrap.sh\n" + // add permission to execute the copied script
                                "/home/ubuntu/bootstrap.sh\n" + // run the script
                                googleservices +
                                "echo '" + awsacademy + "' > /home/ubuntu/awsacademy.pem\n" + // add this file
                                "chmod 400 /home/ubuntu/awsacademy.pem\n" + // add this file
                                "aws s3 cp --recursive s3://" + bucket.getBucketName() + "/client/ /home/ubuntu/ \n" + // update
                                "chmod +x /home/ubuntu/*.sh\n" + // add permission to execute the copied script
                                "/home/ubuntu/clientinstall.sh " + bucket.getBucketName() + " " + lbAddr + " "
                                + googleDrivePath + " " + IPCP + " " + rabbitHost + " " + rabbitPass + " " + useHPA
                                + " " + rabbitPort + "\n"; // run the script

                // System.out.println(userDataString);

                Instance instance = createEc2Instance(name, vpc, instanceAMI, securityGroup, subnet, iKeyPair,
                                userDataString, instanceType, region, exitingRoleArn);

                Tags.of(instance).add("DC", dcNum);

                return instance;
        }

        public Instance createEc2Instance(String name, Vpc vpc, String instanceAMI, ISecurityGroup securityGroup,
                        ISubnet subnet, IKeyPair iKeyPair, String userDataString, InstanceType instanceType,
                        String region, String exitingRoleArn) throws IOException {

                Map<String, String> armUbuntuAMIs = new HashMap<>();
                armUbuntuAMIs.put(region, instanceAMI);

                final IMachineImage armUbuntuMachineImage = MachineImage.genericLinux(armUbuntuAMIs);

                UserData userData = UserData.forLinux();
                userData.addCommands(userDataString);

                IRole existingRole = Role.fromRoleArn(this, "MyExistingRole" + name, exitingRoleArn);

                Instance engineEC2Instance = Instance.Builder.create(this, name)
                                .instanceName(name)
                                .machineImage(armUbuntuMachineImage)
                                .securityGroup(securityGroup)
                                .vpcSubnets(SubnetSelection.builder()
                                                .subnets(new ArrayList<>(List.of(new ISubnet[] { subnet }))).build())
                                .instanceType(instanceType)
                                .keyPair(iKeyPair)
                                .role(existingRole)
                                .vpc(vpc)
                                .userData(userData)
                                .blockDevices(
                                                List.of(
                                                                BlockDevice.builder()
                                                                                .deviceName("/dev/sda1") // Root volume
                                                                                                         // device name
                                                                                .volume(BlockDeviceVolume.ebs(50))
                                                                                .build()))
                                .build();

                // IP público da instância EC2
                CfnOutput.Builder.create(this, "VpcIPOutput" + name)
                                .description("IP público da instância " + name)
                                .value(engineEC2Instance.getInstance().getAttrPublicIp())
                                .build();

                return engineEC2Instance;

        }

        public void addS3Asset(Bucket s3Bucket, String path, String existingRoleArn) {
                // Step 2: Reference the existing IAM role
                IRole existingRole = Role.fromRoleArn(this, "ExistingLabRoleAddAssset", existingRoleArn);

                // Step 3: Create the Lambda function for recursive upload
                Function uploadFilesLambda = Function.Builder.create(this, "RecursiveUploadLambda")
                                .runtime(Runtime.PYTHON_3_9)
                                .handler("upload_files.lambda_handler") // Define the handler function in
                                                                        // upload_files.py
                                .timeout(Duration.minutes(5)) // Set the Lambda function timeout to 5 minutes
                                .code(Code.fromAsset("src/scripts")) // Directory where Lambda code is located
                                .role(existingRole) // Use the existing IAM role
                                .build();

                // Step 4: Create a CloudFormation custom resource to trigger the Lambda for
                // upload
                CfnResource customResource = CfnResource.Builder.create(this, "UploadCustomResource")
                                .type("Custom::S3RecursiveUpload")
                                .properties(Map.of(
                                                "ServiceToken", uploadFilesLambda.getFunctionArn(),
                                                "BucketName", s3Bucket.getBucketName(),
                                                "DirectoryPath", path // The directory path to upload
                                ))
                                .build();
        }

        public Bucket createBucket(String bucketName, String existingRoleArn) {
                // Create the S3 bucket
                Bucket s3Bucket = Bucket.Builder.create(this, bucketName)
                                .removalPolicy(RemovalPolicy.DESTROY) // Ensure the bucket is destroyed on stack
                                                                      // deletion
                                .build();

                // Reference the existing IAM role
                IRole existingRole = Role.fromRoleArn(this, "ExistingLabRoleUploadBucket", existingRoleArn);

                // Create the Lambda function that triggers the S3 bucket cleanup
                Function onEventLambda = Function.Builder.create(this, "OnEventLambda")
                                .runtime(Runtime.PYTHON_3_9)
                                .handler("deleteS3.lambda_handler") // Define the handler
                                .timeout(Duration.minutes(5)) // Set the Lambda function timeout to 5 minutes
                                .code(Code.fromAsset("src/scripts/customlambda"))
                                .role(existingRole) // Use the existing IAM role
                                .build();

                // Create a CloudFormation custom resource that directly invokes the Lambda
                // function
                CfnResource customResource = CfnResource.Builder.create(this, "AutoDeleteCustomResource")
                                .type("Custom::S3AutoDeleteObjects")
                                .properties(Map.of(
                                                "ServiceToken", onEventLambda.getFunctionArn(),
                                                "BucketName", s3Bucket.getBucketName()))
                                .build();

                return s3Bucket;
        }

}

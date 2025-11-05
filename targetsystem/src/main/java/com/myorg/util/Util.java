package com.myorg.util;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.regions.providers.DefaultAwsRegionProviderChain;
import software.amazon.awssdk.services.ec2.Ec2Client;
import software.amazon.awssdk.services.ec2.model.DescribeKeyPairsRequest;
import software.amazon.awssdk.services.ec2.model.DescribeKeyPairsResponse;
import software.amazon.awssdk.services.ec2.model.Ec2Exception;
import software.amazon.awssdk.services.ec2.model.KeyPairInfo;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityRequest;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;


public class Util {

    public String getKeyPairId(String keyName, String regionName) {
        // Create the EC2 client based on the region provided
        Region region = Region.of(regionName);
        Ec2Client ec2 = Ec2Client.builder()
                .region(region)
                .build();

        try {
            // Describe the key pair by name
            DescribeKeyPairsRequest request = DescribeKeyPairsRequest.builder()
                    .keyNames(keyName)
                    .build();

            // Get the response from the EC2 client
            DescribeKeyPairsResponse response = ec2.describeKeyPairs(request);

            // Loop through the key pairs to find the matching key name and return the key ID
            for (KeyPairInfo keyPairInfo : response.keyPairs()) {
                if (keyPairInfo.keyName().equals(keyName)) {
                    return keyPairInfo.keyPairId(); // Return the key pair ID
                }
            }

            // If the key name is not found, return null or throw an exception
            throw new Exception();

        } catch (Exception e) {
            System.err.println("Error fetching Key Pair ID: " + e.getMessage());
            return null; // You can choose to handle the exception differently or propagate it

        } finally {
            ec2.close(); // Always close the EC2 client
        }
    }

    public String getAccount(){
        StsClient stsClient = StsClient.builder()
                .region(Region.AWS_GLOBAL)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();

        // Get the account ID from the STS client
        GetCallerIdentityResponse response = stsClient.getCallerIdentity(GetCallerIdentityRequest.builder().build());
        String accountId = response.account();
        return accountId;
    }

    public String getDefaultRegion(){
        // Use AWS SDK to retrieve the region at synthesis time
        DefaultAwsRegionProviderChain regionProvider = new DefaultAwsRegionProviderChain();
        String region = regionProvider.getRegion().id();
        return region;
    }

}

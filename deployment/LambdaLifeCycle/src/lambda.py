######
# 
# I was working on this to get life cycle configs setup and applied. The way it was only let one config be attached to the domain, and did not attach it to the user profile, so nothing worked. 
# I was adding the updateUserProfile function and changing the updateSageMakerDomainNew function to account for this
# Last test the updateSageMakerDomain function worked, however it did not allow Studio to launch an app.
# 
######
import json, boto3, base64, uuid, logging
import cfnresponse

SageMaker = boto3.client('sagemaker')
# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
responseData = {}

def handler(event, context):
  logger.info(event)
  if event['RequestType'] == 'Create':
    LifeCycleConfigs = getLifeCycleConfigs(event, context, 'Lab')['StudioLifecycleConfigs']
    # if there is an existing lifecycle config, then we should bail. Else, create them
    if len(LifeCycleConfigs) > 0:
      logger.error('Too many configs. Deleting the old.')
      deleteConfig(event, context, 'Lab')

    logger.debug("Create")
    ConfigContentRawShutdown = """
                    # Installs SageMaker Studio's Auto Shutdown Idle Kernel Sessions extension
                    #!/bin/bash
                    
                    set -eux
                    
                    sudo yum -y install wget
                    
                    # Saving the tarball to a file or folder with a '.' prefix will prevent it from cluttering up users' file tree views:
                    mkdir -p .auto-shutdown
                    wget -O .auto-shutdown/extension.tar.gz https://github.com/aws-samples/sagemaker-studio-auto-shutdown-extension/raw/main/sagemaker_studio_autoshutdown-0.1.5.tar.gz
                    pip install .auto-shutdown/extension.tar.gz
                    jlpm config set cache-folder /tmp/yarncache
                    jupyter lab build --debug --minimize=False
                    
                    # restarts jupter server
                    nohup supervisorctl -c /etc/supervisor/conf.d/supervisord.conf restart jupyterlabserver
                    """

    bucket = 'dnblak-dev1'
    region = 'us-west-2'
    solutionName = 'sagemaker-battlesnake-ai/source'
    AccountId = event['ResourceProperties'].get('AccountId')
    S3BucketName = event['ResourceProperties'].get('S3BucketName')
    SageMakerIamRoleArn = event['ResourceProperties'].get('SageMakerIamRoleArn')
    SnakeAPI = event['ResourceProperties'].get('SnakeAPI')
    SagemakerEndPointName = event['ResourceProperties'].get('SagemakerEndPointName')
    SagemakerTrainingInstanceType = event['ResourceProperties'].get('SagemakerTrainingInstanceType')
    SagemakerInferenceInstanceType = event['ResourceProperties'].get('SagemakerInferenceInstanceType')
    ConfigContentRawCopySetup = '''
                    aws s3 cp s3://{bucket}-{region}/{solutionName}/source/ . --recursive
                    touch stack_outputs.json
                    echo '{{' >> stack_outputs.json
                    echo '  "AwsAccountId": "${{AWS::AccountId}}",' >> stack_outputs.json
                    echo '  "AwsRegion": "${{AWS::Region}}",' >> stack_outputs.json
                    echo '  "S3Bucket": "${{S3BucketName}}",' >> stack_outputs.json
                    echo '  "SageMakerIamRoleArn": "${{SageMakerIamRoleArn}}",' >> stack_outputs.json
                    echo '  "SnakeAPI": "${{SnakeAPI}}",' >> stack_outputs.json
                    echo '  "EndPointS3Location": "s3://{bucket}-{region}/{solutionName}/build/model-complete.tar.gz",' >> stack_outputs.json
                    echo '  "SagemakerEndPointName": "${{SagemakerEndPointName}}",' >> stack_outputs.json
                    echo '  "SagemakerTrainingInstanceType": "${{SagemakerTrainingInstanceType}}",' >> stack_outputs.json
                    echo '  "SagemakerInferenceInstanceType": "${{SagemakerInferenceInstanceType}}"' >> stack_outputs.json
                    echo '}}' >> stack_outputs.json
                    '''.format(bucket=bucket,
                                region=region,
                                solutionName=solutionName,
                                AccountId=AccountId, 
                                S3BucketName=S3BucketName, 
                                SageMakerIamRoleArn=SageMakerIamRoleArn, 
                                SnakeAPI=SnakeAPI, 
                                SagemakerEndPointName=SagemakerEndPointName, 
                                SagemakerTrainingInstanceType=SagemakerTrainingInstanceType, 
                                SagemakerInferenceInstanceType=SagemakerInferenceInstanceType)

    createConfig(event, context, ConfigContentRawShutdown,'LabStudioAutoShutdown', 'JupyterServer')
    createConfig(event, context, ConfigContentRawCopySetup,'LabRawCopySetup')
    updateSageMakerDomainNew(event, context, event['ResourceProperties'].get('DomainId'), 'Lab')
    
    # updateSageMakerDomain(event, context, event['ResourceProperties'].get('DomainId'), 'LabStudioAutoShutdown', 'JupyterServerAppSettings')
    # # updateUserProfile(event, context, event['ResourceProperties'].get('DomainId'), 'LabStudioAutoShutdown')
    # updateSageMakerDomain(event, context, event['ResourceProperties'].get('DomainId'), 'LabRawCopySetup')

  elif event['RequestType'] == 'Delete':
    logger.debug("Delete")
    deleteConfig(event, context, 'StudioAutoShutdown')
    deleteConfig(event, context, 'RawCopySetup')

  responseData['Data'] = 'Success'
  cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, event["LogicalResourceId"])
  return {
    'statusCode': 200,
    'body': json.dumps('LifeCycle configs taken care of')
  }

def getLifeCycleConfigs(event, context, NameContains):
  try:
    listResponse = SageMaker.list_studio_lifecycle_configs(NameContains=NameContains)
    logger.info(json.dumps(listResponse, default=str))
    return listResponse
  except Exception as e:
    logger.error(f'Unable to list Studio LifeCycle Configs: {e}')
    responseData['Data'] = f'LifeCycle Configs not found: {e}'
    cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);

def deleteConfig(event, context, NameContains):
  listResponse = getLifeCycleConfigs(event, context, NameContains)
  logger.debug(listResponse)
  
  for config in listResponse['StudioLifecycleConfigs']:
    logger.debug(config['StudioLifecycleConfigName'])
    try: 
      deleteResponse = SageMaker.delete_studio_lifecycle_config(StudioLifecycleConfigName=config['StudioLifecycleConfigName'])
      logger.debug(deleteResponse)
    except Exception as e:
      logger.error(f"Delete failed for:: {config['StudioLifecycleConfigName']} :: reson: {e}")
      responseData['Data'] = f'The LifeCycle was not deleted: {e}'
      cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);

# StudioLifecycleConfigAppType: JupyterServer|KernelGateway
def createConfig(event, context, configContentRaw,StudioLifecycleConfigName,StudioLifecycleConfigAppType='KernelGateway'):
  # Base64 encode the script (required)
  configContent = B64Encode(configContentRaw)
  # Create a UUID to prevent name collisions
  sessionUUID = str(uuid.uuid4())
  # Create the LifeCycle config
  
  try:
    createResponse = SageMaker.create_studio_lifecycle_config(
      StudioLifecycleConfigName=f'{StudioLifecycleConfigName}-{sessionUUID}',
      StudioLifecycleConfigContent=configContent,
      StudioLifecycleConfigAppType=StudioLifecycleConfigAppType
    )
    logger.debug(f'Create response: {createResponse}')
  except Exception as e:
    logger.error(f'Error {e}')
    responseData['Data'] = f'The LifeCycle was not created: {e}'
    cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);

def B64Encode(configContentRaw):
  configContentASCII = configContentRaw.encode('ascii')
  configContentB64 = base64.b64encode(configContentASCII)
  configContent = configContentB64.decode('ascii')
  return configContent

# AppType: JupyterServerAppSettings|KernelGatewayAppSettings
def updateSageMakerDomainNew(event, context, DomainId, NameContains, AppType='KernelGatewayAppSettings'):
  LifeCycleConfigs = getLifeCycleConfigs(event, context, NameContains)['StudioLifecycleConfigs']
  logger.info('In the new domain updater')
  logger.info(len(LifeCycleConfigs))
  for config in LifeCycleConfigs:
    logger.info(config)
    # try:
    #   updateResponse = SageMaker.update_domain(
    #     DomainId=DomainId,
    #     DefaultUserSettings={
    #       AppType: {
    #         'DefaultResourceSpec': {
    #           'InstanceType': 'system',
    #           'LifecycleConfigArn': LifeCycleConfigs[0]['StudioLifecycleConfigArn']
    #         }
    #       }
    #     }
    #   )
    # except Exception as e:
    #   logger.error(f'Adding lifecycle failed. {e}')
    #   responseData['Data'] = 'The LifeCycle was not properly applied. did not update.'
    #   cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);

# AppType: JupyterServerAppSettings|KernelGatewayAppSettings
def updateSageMakerDomain(event, context, DomainId, NameContains, AppType='KernelGatewayAppSettings'):
  LifeCycleConfigs = getLifeCycleConfigs(event, context, NameContains)['StudioLifecycleConfigs']
  if len(LifeCycleConfigs) > 1:
    responseData['Data'] = f'Too many LifeCycle Configs found.'
    cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);
  else:
    try:
      updateResponse = SageMaker.update_domain(
        DomainId=DomainId,
        DefaultUserSettings={
          AppType: {
            'DefaultResourceSpec': {
              'InstanceType': 'system',
              'LifecycleConfigArn': LifeCycleConfigs[0]['StudioLifecycleConfigArn']
            }
          }
        }
      )
    except Exception as e:
      logger.error(f'Adding lifecycle failed. {e}')
      responseData['Data'] = 'The LifeCycle was not properly applied. did not update.'
      cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);


def updateUserProfile(event, context, DomainId, NameContains):
  LifeCycleConfigs = getLifeCycleConfigs(event, context, NameContains)['StudioLifecycleConfigs']

  try: 
    updateResponse = SageMaker.update_user_profile(
      DomainId=DomainId,
      UserProfileName='a',
      UserSettings={
        'JupyterServerAppSettings': {
            'LifecycleConfigArns': [LifeCycleConfigs[0]['StudioLifecycleConfigArn']]
        }
      }
    )
  except Exception as e:
    logger.error(f'Adding lifecycle to user-profile failed. {e}')
    responseData['Data'] = 'The LifeCycle was not properly applied to the user profile. did not update.'
    cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);
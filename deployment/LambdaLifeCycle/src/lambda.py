import json, boto3, base64, uuid, logging
import cfnresponse

SageMaker = boto3.client('sagemaker')
# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
responseData = {}

def lambda_handler(event, context):
  logger.info(event)
  
  if event['RequestType'] == 'Create':
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
    createConfig(event, ConfigContentRawShutdown,'StudioAutoShutdown', 'JupyterServer')
    updateSageMakerDomain(event, event['ResourceProperties'].get('DomainId'), 'StudioAutoShutdown', 'JupyterServerAppSettings')
    
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
                                solutionName=solutionNam,
                                AccountId=AccountId, 
                                S3BucketName=S3BucketName, 
                                SageMakerIamRoleArn=SageMakerIamRoleArn, 
                                SnakeAPI=SnakeAPI, 
                                SagemakerEndPointName=SagemakerEndPointName, 
                                SagemakerTrainingInstanceType=SagemakerTrainingInstanceType, 
                                SagemakerInferenceInstanceType=SagemakerInferenceInstanceType)

    createConfig(event, ConfigContentRawCopySetup,'RawCopySetup')
    updateSageMakerDomain(event, event['ResourceProperties'].get('DomainId'), 'RawCopySetup')

  elif event['RequestType'] == 'Delete':
    logger.debug("Delete")
    deleteConfig(event, 'StudioAutoShutdown')
    deleteConfig(event, 'RawCopySetup')

  responseData['Data'] = 'Success'
  cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData, event["LogicalResourceId"])
  return {
    'statusCode': 200,
    'body': json.dumps('LifeCycle configs taken care of')
  }

def getLifeCycleConfigs(event, NameContains):
  try:
    listResponse = SageMaker.list_studio_lifecycle_configs(NameContains=NameContains)
    return listResponse
  except Exception as e:
    logger.error(f'Unable to list Studio LifeCycle Configs: {e}')
    responseData['Data'] = f'LifeCycle Configs not found: {e}'
    cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);

def deleteConfig(event, NameContains):
  listResponse = getLifeCycleConfigs(event, NameContains)
  logger.debug(listResponse)
  
  for config in listResponse['StudioLifecycleConfigs']:
    print(config['StudioLifecycleConfigName'])
    try: 
      deleteResponse = SageMaker.delete_studio_lifecycle_config(StudioLifecycleConfigName=config['StudioLifecycleConfigName'])
      logger.debug(deleteResponse)
    except Exception as e:
      logger.error(f"Delete failed for:: {config['StudioLifecycleConfigName']} :: reson: {e}")
      responseData['Data'] = f'The LifeCycle was not deleted: {e}'
      cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);

# StudioLifecycleConfigAppType: JupyterServer|KernelGateway
def createConfig(event, configContentRaw,StudioLifecycleConfigName,StudioLifecycleConfigAppType='KernelGateway'):
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
def updateSageMakerDomain(event, DomainId, NameContains, AppType='KernelGatewayAppSettings'):
  LifeCycleConfigs = getLifeCycleConfigs(event, NameContains)['StudioLifecycleConfigs']
  if count(LifeCycleConfigs) > 1:
    responseData['Data'] = f'Too many LifeCycle Configs found.'
    cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);
  else:
    try:
      updateResponse = sagemaker.update_domain(
        DomainId=DomainId,
        DefaultUserSettings={
          AppType: {
            'DefaultResourceSpec': {
              'LifecycleConfigArn': LifecycleConfigArn
            }
          }
        }
      )
    except Exception as e:
      logger.error(f'Adding lifecycle failed.{e}')
      responseData['Data'] = 'The LifeCycle was not properly applied. did not update.'
      cfnresponse.send(event, context, cfnresponse.FAILED, responseData, event["LogicalResourceId"]);
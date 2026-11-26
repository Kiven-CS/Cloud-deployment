targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment used to generate unique resource names.')
param environmentName string

@minLength(1)
@description('Primary location for all resources.')
param location string

@description('ID of the user or app that receives data access for local development.')
param principalId string = ''

@allowed([
  'User'
  'ServicePrincipal'
])
param principalType string = 'User'

param storageAccountName string = ''
param containerAppsEnvName string = ''
param containerAppsAppName string = ''
param containerRegistryName string = ''
param resourceGroupName string = ''
param containerImageName string = ''
param serviceName string = 'aca'

var abbreviations = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : '${abbreviations.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}

module identity './core/security/user-assigned-identity.bicep' = {
  name: 'identity'
  scope: resourceGroup
  params: {
    name: 'hello-azd-identity'
    location: location
    tags: tags
  }
}

module storage './core/storage/storage-account.bicep' = {
  name: 'storage'
  scope: resourceGroup
  params: {
    name: !empty(storageAccountName) ? storageAccountName : '${abbreviations.storageStorageAccounts}${resourceToken}'
    location: location
    tags: tags
    containers: [
      { name: 'attachments' }
    ]
    tables: [
      { name: 'tickets' }
    ]
  }
}

module userBlobAccess './core/security/role.bicep' = {
  name: 'user-blob-access'
  scope: resourceGroup
  params: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  }
}

module identityBlobAccess './core/security/role.bicep' = {
  name: 'identity-blob-access'
  scope: resourceGroup
  params: {
    principalId: identity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  }
}

module userTableAccess './core/security/role.bicep' = {
  name: 'user-table-access'
  scope: resourceGroup
  params: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  }
}

module identityTableAccess './core/security/role.bicep' = {
  name: 'identity-table-access'
  scope: resourceGroup
  params: {
    principalId: identity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  }
}

module containerAppsEnvironment './core/host/container-apps-environment.bicep' = {
  name: 'container-apps-environment'
  scope: resourceGroup
  params: {
    name: !empty(containerAppsEnvName) ? containerAppsEnvName : '${abbreviations.appManagedEnvironments}${resourceToken}'
    location: location
    tags: tags
  }
}

module containerRegistry './core/host/container-registry.bicep' = {
  name: 'container-registry'
  scope: resourceGroup
  params: {
    name: !empty(containerRegistryName) ? containerRegistryName : '${abbreviations.containerRegistryRegistries}${resourceToken}'
    location: location
    tags: tags
  }
}

module web './core/host/container-app.bicep' = {
  name: serviceName
  scope: resourceGroup
  params: {
    name: !empty(containerAppsAppName) ? containerAppsAppName : '${abbreviations.appContainerApps}${resourceToken}'
    containerAppsEnvironmentName: containerAppsEnvironment.outputs.name
    containerRegistryName: containerRegistry.outputs.name
    identityName: identity.outputs.name
    location: location
    tags: union(tags, { 'azd-service-name': serviceName })
    targetPort: 8080
    imageName: !empty(containerImageName) ? containerImageName : 'nginx:alpine'
    env: [
      {
        name: 'AZURE_MANAGED_IDENTITY_CLIENT_ID'
        value: identity.outputs.clientId
      }
      {
        name: 'STORAGE_URL'
        value: storage.outputs.blobEndpoint
      }
      {
        name: 'TABLES_URL'
        value: storage.outputs.tableEndpoint
      }
    ]
  }
}

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = containerRegistry.outputs.name
output AZURE_CONTAINER_APP_ENDPOINT string = web.outputs.uri
output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_USER_ASSIGNED_IDENTITY_NAME string = identity.outputs.name
output STORAGE_URL string = storage.outputs.blobEndpoint
output TABLES_URL string = storage.outputs.tableEndpoint

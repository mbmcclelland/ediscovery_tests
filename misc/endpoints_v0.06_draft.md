# v0.06 write-path capture — draft

_Captured 2026-05-11T21:58:29.108499 via `playwright_capture_writes.py`_

## Candidate write endpoints

| Endpoint | Calls | Statuses | Sample req body keys |
|---|---:|---|---|
| `orgManager/getNfsMounts` | 1 | [200] | contextHandle, remoteHost, requestHandle, timeoutSeconds |
| `permissionManager/getCombinedUserRole` | 2 | [200] | contextHandle, entityHandle, requestHandle |
| `projectManager/getUpdateStatus` | 2 | [200] | contextHandle, projectHandle, requestHandle, timestamp, updateStatusTypes |
| `realmManager/getLicensedFeatures` | 1 | [200] | contextHandle, requestHandle |
| `realmManager/listCustomersForStorageFacility` | 1 | [200] | contextHandle, handle, requestHandle |
| `realmManager/listNodes` | 1 | [200] | contextHandle, requestHandle |
| `storageAreaManager/countCustomersForFacility` | 1 | [200] | contextHandle, handle, requestHandle |
| `viewManager/validateName` | 1 | [200] | contextHandle, name, objectType, requestHandle, systemScope |

## Raw bodies (one per endpoint)

### `orgManager/getNfsMounts`

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "remoteHost": "192.168.58.128",
  "timeoutSeconds": 10
}
```
_Response status: 200_

### `permissionManager/getCombinedUserRole`

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "entityHandle": "super_system_customer"
}
```
_Response status: 200_

### `projectManager/getUpdateStatus`

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "projectHandle": 0,
  "timestamp": 0,
  "updateStatusTypes": [
    "PROJECT",
    "ADMIN_REQUEST",
    "TASK",
    "STORAGE"
  ]
}
```
_Response status: 200_

### `realmManager/getLicensedFeatures`

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer"
}
```
_Response status: 200_

### `realmManager/listCustomersForStorageFacility`

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "handle": "95"
}
```
_Response status: 200_

### `realmManager/listNodes`

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer"
}
```
_Response status: 200_

### `storageAreaManager/countCustomersForFacility`

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "handle": "90"
}
```
_Response status: 200_

### `viewManager/validateName`

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "name": "captureDoc215710",
  "objectType": "STORAGE",
  "systemScope": true
}
```
_Response status: 200_

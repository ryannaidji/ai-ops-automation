# Technical FAQ (fictional company "Acme Cloud")

## Status page
Current incidents and maintenance windows are posted at status.acme.example. Subscribe there for email updates.

## Error 429 Too Many Requests
The API allows 100 requests per minute per API key. Back off and retry with exponential delay. Higher limits are available on the Business plan.

## Error 500 on file upload
Uploads larger than 2 GB fail with error 500. Split the file or use the multipart upload endpoint.

## Sync not working
Sign out and back in, then check that the desktop app is version 4.2 or later. Clearing the local cache (Settings > Advanced > Clear cache) fixes most sync problems.

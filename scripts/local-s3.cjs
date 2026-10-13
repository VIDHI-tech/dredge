const path = require('node:path');
const fs = require('node:fs');
const S3rver = require('s3rver');

const directory = path.join(__dirname, '..', '.local', 's3');
const port = Number.parseInt(process.env.S3RVER_PORT || '5001', 10);
fs.mkdirSync(directory, { recursive: true });

new S3rver({
  address: '127.0.0.1',
  port,
  directory,
  configureBuckets: [{ name: 'dredge-local' }],
}).run().then(() => {
  console.log(`Local S3 storage ready at http://127.0.0.1:${port}`);
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

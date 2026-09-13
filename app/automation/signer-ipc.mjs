import http from "node:http";
import { chmodSync, existsSync } from "node:fs";
import { fail, safeCode, ServiceError } from "./errors.mjs";

export class SignerClient {
  constructor(socketPath) {
    this.socketPath = socketPath;
  }
  async health() {
    return new Promise((resolve, reject) => {
      const req=http.get({socketPath:this.socketPath,path:"/health",timeout:5000},res=>{
        let body="";res.on("data",chunk=>{body+=chunk;if(body.length>2048)req.destroy();});
        res.on("end",()=>{try{if(res.statusCode!==200)throw Error();resolve(JSON.parse(body));}catch{reject(new ServiceError("signer_unavailable"));}});
        res.on("error",()=>reject(new ServiceError("signer_unavailable")));
      });
      req.on("error",()=>reject(new ServiceError("signer_unavailable")));req.on("timeout",()=>req.destroy());
    });
  }
  async sign(input) {
    return new Promise((resolve, reject) => {
      const request = http.request(
        {
          socketPath: this.socketPath,
          path: "/sign",
          method: "POST",
          headers: { "Content-Type": "application/json" },
          timeout: 15_000,
        },
        (response) => {
          let body = "";
          response.on("data", (chunk) => {
            body += chunk;
            if (body.length > 500_000) {
              reject(new ServiceError("signer_unavailable"));
              request.destroy();
            }
          });
          response.on("error", () =>
            reject(new ServiceError("signer_unavailable")),
          );
          response.on("end", () => {
            try {
              const data = JSON.parse(body);
              if (
                response.statusCode !== 200 ||
                !/^0x[0-9a-f]+$/i.test(data.signed)
              )
                return reject(
                  new ServiceError(data.code ?? "signer_unavailable"),
                );
              resolve(data.signed);
            } catch {
              reject(new ServiceError("signer_unavailable"));
            }
          });
        },
      );
      request.on("error", () => reject(new ServiceError("signer_unavailable")));
      request.on("timeout", () => request.destroy());
      request.end(JSON.stringify(input));
    });
  }
}
export async function serveSigner(socketPath, signer) {
  // The service manager owns the runtime directory. Never unlink an existing
  // socket: it may belong to another active signer using this nonce ledger.
  if (existsSync(socketPath)) fail("signer_socket_already_exists");
  let busy = false;
  const server = http.createServer(async (req, res) => {
    if (req.method === "GET" && req.url === "/health") {
      res.writeHead(200,{"Content-Type":"application/json"}).end(JSON.stringify({address:signer.account.address,chainId:signer.config.chainId}));return;
    }
    if (req.method !== "POST" || req.url !== "/sign") {
      res.writeHead(404).end();
      return;
    }
    if (busy) {
      res.writeHead(503).end('{"code":"signer_busy"}');
      return;
    }
    busy = true;
    try {
      let body = "";
      for await (const chunk of req) {
        body += chunk;
        if (body.length > 450_000)
          throw new ServiceError("signer_request_too_large", 413);
      }
      const signed = await signer.sign(JSON.parse(body));
      res
        .writeHead(200, { "Content-Type": "application/json" })
        .end(JSON.stringify({ signed }));
    } catch (error) {
      res
        .writeHead(error instanceof ServiceError ? error.status : 503)
        .end(JSON.stringify({ code: safeCode(error) }));
    } finally {
      busy = false;
    }
  });
  server.requestTimeout = 15000;
  server.headersTimeout = 10000;
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(socketPath, resolve);
  });
  chmodSync(socketPath, 0o660);
  return server;
}

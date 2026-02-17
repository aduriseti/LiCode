import express, { type Express, type Request, type Response } from "express";
import { Server } from "socket.io";
import http, { type IncomingMessage, type Server as HttpServer } from "http";
import { type Duplex } from "stream";
import WebSocket, { WebSocketServer } from "ws";
import fs from "fs";
import path from "path";
import type { TerminalManager } from "./terminal.manager";

export function createDashboardApp() {
    const app: Express = express();
    const server: HttpServer = http.createServer(app);
    const io: Server = new Server(server, { destroyUpgrade: false });

    const htmlPath = path.join(__dirname, "../plugins/dashboard.html");

    app.get('/', (req: Request, res: Response) => {
        try {
            const html = fs.readFileSync(htmlPath, "utf-8");
            res.send(html);
        } catch (err) {
            res.status(500).send("Error loading dashboard HTML");
        }
    });

    // Sets up WebSocket proxy for terminal connections.
    // Browser connects to ws://<dashboard>/terminal/<agent_id>
    // and gets proxied to the helper's WebSocket on 127.0.0.1:<port>.
    function setupTerminalProxy(terminalManager: TerminalManager) {
        const wss = new WebSocketServer({ noServer: true });

        server.on("upgrade", (req: IncomingMessage, socket: Duplex, head: Buffer) => {
            const url = req.url || "";
            const match = url.match(/^\/terminal\/(.+)$/);
            if (!match) return; // Let Socket.IO handle its own upgrades

            const agentId = decodeURIComponent(match[1]);
            const helperPort = terminalManager.getHelperPort(agentId);

            if (!helperPort) {
                socket.write("HTTP/1.1 404 Not Found\r\n\r\n");
                socket.destroy();
                return;
            }

            // Complete the WebSocket handshake with the browser
            wss.handleUpgrade(req, socket, head, (browserWs) => {
                const helperWs = new WebSocket(`ws://127.0.0.1:${helperPort}`);

                helperWs.on("message", (data, isBinary) => {
                    if (browserWs.readyState === WebSocket.OPEN) {
                        browserWs.send(isBinary ? data : data.toString());
                    }
                });

                browserWs.on("message", (data) => {
                    if (helperWs.readyState === WebSocket.OPEN) {
                        helperWs.send(data);
                    }
                });

                browserWs.on("close", () => helperWs.close());
                helperWs.on("close", () => browserWs.close());
                helperWs.on("error", () => browserWs.close());
                browserWs.on("error", () => helperWs.close());
            });
        });
    }

    return { app, server, io, setupTerminalProxy };
}
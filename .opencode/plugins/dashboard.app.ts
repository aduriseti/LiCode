import express, { type Express, type Request, type Response } from "express";
import { Server } from "socket.io";
import http, { type Server as HttpServer } from "http";
import fs from "fs";
import path from "path";

export function createDashboardApp() {
    const app: Express = express();
    const server: HttpServer = http.createServer(app);
    const io: Server = new Server(server);

    // Read HTML from file to keep things clean and maintainable
    const htmlPath = path.join(__dirname, "dashboard.html");

    app.get('/', (req: Request, res: Response) => {
        try {
            const html = fs.readFileSync(htmlPath, "utf-8");
            res.send(html);
        } catch (err) {
            res.status(500).send("Error loading dashboard HTML");
        }
    });

    return { app, server, io };
}
import { rest } from 'msw';
import { setupServer } from 'msw/node';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import WS from 'jest-websocket-mock';

import React from 'react';
import DotBots from './DotBots';

let currentActive = "4242";

const server = setupServer(
    rest.get('/controller/dotbots', (req, res, ctx) => {
        return res(ctx.json(
            [
                {
                    address: "2020",
                    application: "DotBot",
                    swarm: "0000",
                    last_seen: 123.4,
                    lh2_position: {x: 200.0, y: 200.0, z: 0.0},
                },
                {
                    address: "3131",
                    application: "DotBot",
                    swarm: "0000",
                    last_seen: 123.4,
                    lh2_position: {x: 100.0, y: 100.0, z: 0.0},
                },
                {
                    address: "4242",
                    application: "DotBot",
                    swarm: "0000",
                    last_seen: 123.4,
                },
            ]
        ));
    }),
    rest.get('/controller/dotbot_address', (req, res, ctx) => {
        return res(ctx.json({"address": currentActive}));
    }),
    rest.put('/controller/dotbot_address', (req, res, ctx) => {
        req.json().then((data) => {
            currentActive = data.address;
        });
        return res();
    }),
    rest.get('/controller/lh2/calibration', (req, res, ctx) => {
        return res(ctx.json({state: "done"}));
    }),
);

const wsServer = new WS("ws://localhost:8000/controller/ws/status");
const user = userEvent.setup();

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

test('DotBots main page', async () => {
    render(<DotBots />);
    await waitFor(() => expect(screen.getByText("Available DotBots")).toBeVisible());
    await waitFor(() => expect(screen.getAllByText('activate')[0]).toBeVisible());
    await waitFor(() => expect(screen.getByText('active')).toBeVisible());

    await user.click(screen.getAllByText('activate')[0]);
    await new Promise(r => setTimeout(r, 100));
    expect(currentActive).toEqual("2020");

    // send reload command via websocket
    await waitFor(() => wsServer.send('{"cmd":"reload"}'));
    expect(currentActive).toEqual("2020");

    // Click on the active one => no more current active dotbot
    await user.click(screen.getByText('active'));
    await new Promise(r => setTimeout(r, 200));
    expect(currentActive).toEqual("2020");

    await user.click(screen.getAllByText('activate')[0]);
    await new Promise(r => setTimeout(r, 100));
    expect(currentActive).toEqual("3131");
});

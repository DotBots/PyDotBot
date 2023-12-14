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
                    application: 0,
                    swarm: "0000",
                    last_seen: 123.4,
                    status: 0,
                    lh2_position: {x: 200.0, y: 200.0, z: 0.0},
                    position_history: [],
                    waypoints: [],
                },
                {
                    address: "3131",
                    application: 0,
                    swarm: "0000",
                    last_seen: 123.4,
                    status: 0,
                    lh2_position: {x: 100.0, y: 100.0, z: 0.0},
                    position_history: [],
                    waypoints: [],
                },
                {
                    address: "4242",
                    application: 0,
                    swarm: "0000",
                    last_seen: 123.4,
                    status: 0,
                    position_history: [],
                    waypoints: [],
                },
                {
                    address: "5353",
                    application: 0,
                    swarm: "0000",
                    last_seen: 123.4,
                    status: 2,
                    lh2_position: {x: 100.0, y: 100.0, z: 0.0},
                    position_history: [],
                    waypoints: [],
                },
                {
                    address: "5151",
                    application: 1,
                    swarm: "0000",
                    last_seen: 123.4,
                    status: 2,
                    gps_position: {latitude: 48.832313766146896, longitude: 2.4126897594949184},
                    position_history: [],
                    waypoints: [],
                },
                {
                    address: "5252",
                    application: 1,
                    swarm: "0000",
                    last_seen: 123.4,
                    status: 2,
                    gps_position: {latitude: 48.832313766146896, longitude: 2.4126897594949184},
                    position_history: [],
                    waypoints: [],
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
    rest.put('/controller/dotbots/:address/:application/move_raw', (req, res, ctx) => {
        return res();
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
    await waitFor(() => expect(screen.getByText("Available SailBots")).toBeVisible());

    await user.click(screen.getAllByText('alive')[0]);
    await new Promise(r => setTimeout(r, 100));
    expect(currentActive).toEqual("2020");

    // send reload command via websocket
    await waitFor(() => wsServer.send('{"cmd":"reload"}'));
    expect(currentActive).toEqual("2020");
});

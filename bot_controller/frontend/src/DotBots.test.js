import { rest } from 'msw';
import { setupServer } from 'msw/node';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { act } from 'react-dom/test-utils';
import '@testing-library/jest-dom';

import React from 'react';
import DotBots from './DotBots';

const server = setupServer(
    rest.get('/controller/dotbots', (req, res, ctx) => {
        return res(ctx.json(
            [
                {
                    address: "2020",
                    application: "DotBot",
                    swarm: "0000",
                    last_seen: 123.4,
                },
                {
                    address: "3131",
                    application: "DotBot",
                    swarm: "0000",
                    last_seen: 123.4,
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
        return res(ctx.json({"address": "4242"}));
    }),
    rest.put('/controller/dotbot_address', (req, res, ctx) => {
        return res();
    }),
);

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

test('DotBots main page', async () => {
    await act(async () => {
        render(<DotBots />);
    });
    await waitFor(() => expect(screen.getByText("Available DotBots")).toBeVisible());
    await waitFor(() => expect(screen.getByText("Address")).toBeVisible());
    await waitFor(() => expect(screen.getByText("Application")).toBeVisible());
    await waitFor(() => expect(screen.getByText("Swarm ID")).toBeVisible());
    await waitFor(() => expect(screen.getByText("Last seen")).toBeVisible());
    await waitFor(() => expect(screen.getByText("State")).toBeVisible());
    await waitFor(() => expect(screen.getAllByText('activate')[0]).toBeVisible());
    await waitFor(() => expect(screen.getByText('active')).toBeVisible());

    await act(async () => {
        fireEvent.click((screen.getAllByText('activate')[0]));
    });
});

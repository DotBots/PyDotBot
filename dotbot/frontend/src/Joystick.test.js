import { rest } from 'msw';
import { setupServer } from 'msw/node';

import { render, screen, waitFor } from '@testing-library/react';

import { act } from 'react-dom/test-utils';
import '@testing-library/jest-dom';

import React from 'react';
import { Joystick } from './Joystick';

const server = setupServer(
  rest.put('/controller/dotbots/:address/:application/move_raw', (req, res, ctx) => {
      return res();
  }),
);

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const fireMouseEvent = function (type, elem, centerX, centerY) {
  const evt = document.createEvent('MouseEvents');
  evt.initMouseEvent(
      type,
      true,
      true,
      window,
      1,
      1,
      1,
      centerX,
      centerY,
      false,
      false,
      false,
      false,
      0,
      elem
  );
  return elem.dispatchEvent(evt);
};

const dragJoystick = async (elemDrag) => {
  await act(async () => {
      // calculate positions
      let pos = elemDrag.getBoundingClientRect();
      const center1X = Math.floor((pos.left + pos.right) / 2);
      const center1Y = Math.floor((pos.top + pos.bottom) / 2);

      const center2X = Math.floor((pos.left + pos.right + 10) / 2);
      const center2Y = Math.floor((pos.top + pos.bottom + 10) / 2);

      // mouse over dragged element and mousedown
      fireMouseEvent('mousemove', elemDrag, center1X, center1Y);
      fireMouseEvent('mouseenter', elemDrag, center1X, center1Y);
      fireMouseEvent('mouseover', elemDrag, center1X, center1Y);
      fireMouseEvent('mousedown', elemDrag, center1X, center1Y);

      // start dragging process over to drop target
      const dragStarted = fireMouseEvent(
          'dragstart',
          elemDrag,
          center1X,
          center1Y
      );
      if (!dragStarted) {
          return;
      }

      fireMouseEvent('drag', elemDrag, center1X, center1Y);
      fireMouseEvent('mousemove', elemDrag, center1X, center1Y);
      await new Promise(r => setTimeout(r, 100));
      fireMouseEvent('drag', elemDrag, center2X, center2Y);
      await new Promise(r => setTimeout(r, 100));
      fireMouseEvent('dragend', elemDrag, center2X, center2Y);
      fireMouseEvent('mouseup', elemDrag, center2X, center2Y);
  });
};

test('Joystick test', async () => {
  render(<Joystick />);
  await waitFor(() => expect(screen.getByRole("region")).toBeVisible());
  await waitFor(() => expect(screen.getByRole("button")).toBeVisible());
  await dragJoystick(screen.getByRole("button"));
});

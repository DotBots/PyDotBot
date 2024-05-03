// SPDX-FileCopyrightText: 2022-present Inria
// SPDX-FileCopyrightText: 2022-present Filip Maksimovic <filip.maksimovic@inria.fr>
// SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
//
// SPDX-License-Identifier: BSD-3-Clause


#include <stdint.h>

static const uint32_t _polynomials[4] = {
    0x0001D258,
    0x00017E04,
    0x0001FF6B,
    0x00013F67,
};

static const uint32_t _end_buffers[4][16] = {
    {
        // p0
        0x00000000000000001,  // [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1] starting seed, little endian
        0b10101010110011101,  // 1/16 way through
        0b10001010101011010,  // 2/16 way through
        0b11001100100000010,  // 3/16 way through
        0b01100101100011111,  // 4/16 way through
        0b10010001101011110,  // 5/16 way through
        0b10100011001011111,  // 6/16 way through
        0b11110001010110001,  // 7/16 way through
        0b10111000110011011,  // 8/16 way through
        0b10100110100011110,  // 9/16 way through
        0b11001101100010000,  // 10/16 way through
        0b01000101110011111,  // 11/16 way through
        0b11100101011110101,  // 12/16 way through
        0b01001001110110111,  // 13/16 way through
        0b11011100110011101,  // 14/16 way through
        0b10000110101101011,  // 15/16 way through
    },
    {
        // p1
        0x00000000000000001,  // [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1] starting seed, little endian
        0b11010000110111110,  // 1/16 way through
        0b10110111100111100,  // 2/16 way through
        0b11000010101101111,  // 3/16 way through
        0b00101110001101110,  // 4/16 way through
        0b01000011000110100,  // 5/16 way through
        0b00010001010011110,  // 6/16 way through
        0b10100101111010001,  // 7/16 way through
        0b10011000000100001,  // 8/16 way through
        0b01110011011010110,  // 9/16 way through
        0b00100011101000011,  // 10/16 way through
        0b10111011010000101,  // 11/16 way through
        0b00110010100110110,  // 12/16 way through
        0b01000111111100110,  // 13/16 way through
        0b10001101000111011,  // 14/16 way through
        0b00111100110011100,  // 15/16 way through
    },
    {
        // p2
        0x00000000000000001,  // [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1] starting seed, little endian
        0b00011011011000100,  // 1/16 way through
        0b01011101010010110,  // 2/16 way through
        0b11001011001101010,  // 3/16 way through
        0b01110001111011010,  // 4/16 way through
        0b10110110011111010,  // 5/16 way through
        0b10110001110000001,  // 6/16 way through
        0b10001001011101001,  // 7/16 way through
        0b00000010011101011,  // 8/16 way through
        0b01100010101111011,  // 9/16 way through
        0b00111000001101111,  // 10/16 way through
        0b10101011100111000,  // 11/16 way through
        0b01111110101111111,  // 12/16 way through
        0b01000011110101010,  // 13/16 way through
        0b01001011100000011,  // 14/16 way through
        0b00010110111101110,  // 15/16 way through
    },
    {
        // p3
        0x00000000000000001,  // [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1] starting seed, little endian
        0b11011011110010110,  // 1/16 way through
        0b11000100000001101,  // 2/16 way through
        0b11100011000010110,  // 3/16 way through
        0b00011111010001100,  // 4/16 way through
        0b11000001011110011,  // 5/16 way through
        0b10011101110001010,  // 6/16 way through
        0b00001011001111000,  // 7/16 way through
        0b00111100010000101,  // 8/16 way through
        0b01001111001010100,  // 9/16 way through
        0b01011010010110011,  // 10/16 way through
        0b11111101010001100,  // 11/16 way through
        0b00110101011011111,  // 12/16 way through
        0b01110110010101011,  // 13/16 way through
        0b00010000110100010,  // 14/16 way through
        0b00010111110101110,  // 15/16 way through
    },
};

uint32_t reverse_count_p(uint8_t index, uint32_t bits)
{
    uint32_t count       = 0;
    uint32_t buffer      = bits & 0x0001FFFFF;  // initialize buffer to initial bits, masked
    uint8_t  ii          = 0;                   // loop variable for cumulative sum
    uint32_t result      = 0;
    uint32_t b17         = 0;
    uint32_t masked_buff = 0;
    while (buffer != _end_buffers[index][0])  // do until buffer reaches one of the saved states
    {
        b17         = buffer & 0x00000001;               // save the "newest" bit of the buffer
        buffer      = (buffer & (0x0001FFFE)) >> 1;      // shift the buffer right, backwards in time
        masked_buff = (buffer) & (_polynomials[index]);  // mask the buffer w/ the selected polynomial
        for (ii = 0; ii < 17; ii++) {
            result = result ^ (((masked_buff) >> ii) & (0x00000001));  // cumulative sum of buffer&poly
        }
        result = result ^ b17;
        buffer = buffer | (result << 16);  // update buffer w/ result
        result = 0;                        // reset result
        count++;
        for (uint8_t idx = 1; idx < 16; idx++) {
            if ((buffer ^ _end_buffers[index][idx]) == 0x00000000) {
                count  = count + 8192 * idx - 1;
                buffer = _end_buffers[index][0];
            }
        }
    }
    return count;
}

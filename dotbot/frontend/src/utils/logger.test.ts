import { vi, describe, test, expect, beforeEach, beforeAll } from 'vitest';

// pino() is called at logger.ts module load time, so we can't use vi.mock (hoisted)
// with a let variable — it would be in the TDZ. Use vi.doMock + dynamic import instead.

const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

let capturedWrite: ((o: unknown) => void) | null = null;
let capturedLevel: string | undefined;

beforeAll(async () => {
  vi.resetModules(); // ensure a fresh logger.ts load

  vi.doMock('pino', () => {
    const mockLogger: Record<string, unknown> = {};
    mockLogger.child = vi.fn(() => mockLogger);
    const pinoFn = vi.fn(
      (opts: { level?: string; browser?: { write?: (o: unknown) => void } }) => {
        capturedWrite = opts?.browser?.write ?? null;
        capturedLevel = opts?.level;
        return mockLogger;
      },
    );
    (pinoFn as unknown as { stdTimeFunctions: unknown }).stdTimeFunctions = {
      isoTime: vi.fn(),
    };
    return { default: pinoFn };
  });

  await import('./logger'); // triggers pino() → sets capturedWrite / capturedLevel
});

beforeEach(() => consoleSpy.mockClear());

// Helper: invoke the captured write callback with a synthetic log object
const callWrite = (level: number, msg: string, module?: string) => {
  capturedWrite!({
    time: '2026-04-14T09:00:00.000Z',
    level,
    msg,
    ...(module !== undefined ? { module } : {}),
  });
};

// ─── pino initialisation ─────────────────────────────────────────────────────

test('logger passes a write function to pino browser config', () => {
  expect(capturedWrite).toBeTypeOf('function');
});

test('logger level is a non-empty string (defaulting to "info" or VITE_LOG_LEVEL)', () => {
  expect(typeof capturedLevel).toBe('string');
  expect(capturedLevel!.length).toBeGreaterThan(0);
});

// ─── levelToLabel: label strings ─────────────────────────────────────────────

describe('levelToLabel: label strings', () => {
  test('level 50 (error) produces [ERROR] label', () => {
    callWrite(50, 'boom');
    expect(consoleSpy.mock.calls[0][0]).toContain('[ERROR]');
  });

  test('level 40 (warn) produces [WARNING] label', () => {
    callWrite(40, 'careful');
    expect(consoleSpy.mock.calls[0][0]).toContain('[WARNING]');
  });

  test('level 30 (info) produces [INFO] label', () => {
    callWrite(30, 'hello');
    expect(consoleSpy.mock.calls[0][0]).toContain('[INFO]');
  });

  test('level 20 (debug) produces [DEBUG] label', () => {
    callWrite(20, 'detail');
    expect(consoleSpy.mock.calls[0][0]).toContain('[DEBUG]');
  });

  test('level 10 (trace, ≤20) also produces [DEBUG] label', () => {
    callWrite(10, 'trace');
    expect(consoleSpy.mock.calls[0][0]).toContain('[DEBUG]');
  });
});

// ─── levelToLabel: CSS styles ────────────────────────────────────────────────

describe('levelToLabel: CSS styles', () => {
  test('error level uses red bold style', () => {
    callWrite(50, 'err');
    expect(consoleSpy.mock.calls[0][1]).toContain('color:red');
    expect(consoleSpy.mock.calls[0][1]).toContain('font-weight:bold');
  });

  test('warn level uses yellow bold style', () => {
    callWrite(40, 'warn');
    expect(consoleSpy.mock.calls[0][1]).toContain('color:yellow');
    expect(consoleSpy.mock.calls[0][1]).toContain('font-weight:bold');
  });

  test('info level uses white bold style', () => {
    callWrite(30, 'info');
    expect(consoleSpy.mock.calls[0][1]).toContain('color:white');
    expect(consoleSpy.mock.calls[0][1]).toContain('font-weight:bold');
  });

  test('debug level uses green bold style', () => {
    callWrite(20, 'dbg');
    expect(consoleSpy.mock.calls[0][1]).toContain('color:green');
    expect(consoleSpy.mock.calls[0][1]).toContain('font-weight:bold');
  });

  test('third console.log arg is always "color:white" (reset style)', () => {
    callWrite(30, 'reset');
    expect(consoleSpy.mock.calls[0][2]).toBe('color:white');
  });
});

// ─── write callback: format string content ───────────────────────────────────

describe('write callback: format string', () => {
  test('message text appears in the format string', () => {
    callWrite(30, 'hello world');
    expect(consoleSpy.mock.calls[0][0]).toContain('hello world');
  });

  test('timestamp appears in the format string', () => {
    callWrite(30, 'ts');
    expect(consoleSpy.mock.calls[0][0]).toContain('2026-04-14T09:00:00.000Z');
  });

  test('module name appears in the format string when set', () => {
    callWrite(30, 'msg', 'myModule');
    expect(consoleSpy.mock.calls[0][0]).toContain('myModule');
    expect(consoleSpy.mock.calls[0][0]).toContain('msg');
  });

  test('module segment adds " - <name>" before message', () => {
    callWrite(30, 'msg', 'mod42');
    expect(consoleSpy.mock.calls[0][0]).toContain(' - mod42 - msg');
  });

  test('no module field does not add an extra " - " compared to having a module', () => {
    callWrite(30, 'no mod');
    const fmtNoModule = consoleSpy.mock.calls[0][0] as string;
    expect(fmtNoModule).not.toContain('undefined');
    consoleSpy.mockClear();

    callWrite(30, 'with mod', 'someModule');
    const fmtWithModule = consoleSpy.mock.calls[0][0] as string;

    // With a module there is one more " - " than without
    const countNoMod = (fmtNoModule.match(/ - /g) ?? []).length;
    const countWithMod = (fmtWithModule.match(/ - /g) ?? []).length;
    expect(countWithMod).toBe(countNoMod + 1);
  });
});

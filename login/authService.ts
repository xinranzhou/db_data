import Store from 'electron-store';
import { app, session } from 'electron';
import { IBaseResponse } from '../../types';
import fetch from 'node-fetch';
import os from 'node:os';
import crypto from 'node:crypto';
import path from 'node:path';
import {
  APP_NAME,
  AUTH_API_BASE_URL_DEV,
  AUTH_API_BASE_URL_PROD,
  AUTH_TOKEN_TTL_MS,
} from '@/constant';
import { isPlainRecord } from '@/main/util';
const electronApp = app as unknown as any;
interface IElectronKeyValueStore<T extends Record<string, unknown>> {
  get<K extends keyof T>(key: K): T[K];
  set<K extends keyof T>(key: K, value: T[K]): void;
  delete<K extends keyof T>(key: K): void;
}

/** 创建 electron-store 实例（中文注释）
 * 说明：测试环境无法写入系统 Preferences 目录，因此落到项目目录下
 * 返回：electron-store 实例（用于保存 token 与设备信息）
 */
function createElectronStore(): Store<{
  token?: string;
  token_expires_at?: number | string;
  user?: { username: string };
  device_id?: string;
}> {
  const isElectronRuntime = !!(process.versions && process.versions.electron);
  if (isElectronRuntime) {
    return new Store();
  }
  return new Store({
    projectName: APP_NAME,
    cwd: path.join(process.cwd(), '.electron-store'),
  });
}

/** 获取鉴权服务 baseURL（中文注释）
 * 说明：开发环境默认走本地 member-service；生产环境默认走线上地址；可用环境变量覆盖
 * 返回：baseURL（不带末尾 /）
 */
function getAuthApiBaseUrl(): string {
  const isPackaged = electronApp?.isPackaged;
  const base = !isPackaged ? AUTH_API_BASE_URL_DEV : AUTH_API_BASE_URL_PROD;
  return base.replace(/\/+$/, '');
}

const rawStore = createElectronStore();
const store = rawStore as unknown as IElectronKeyValueStore<{
  token?: string;
  token_expires_at?: number | string;
  user?: { username: string };
  device_id?: string;
}>;

const AUTH_TOKEN_COOKIE_NAME = 'meituan_assistant_token';

function canUseElectronSession(): boolean {
  return !!(process.versions && process.versions.electron && session?.defaultSession?.cookies);
}

function getAuthCookieUrl(): string {
  try {
    const baseUrl = getAuthApiBaseUrl();
    return new URL(baseUrl).origin;
  } catch {
    return 'https://admin.aowu100.com';
  }
}

async function setTokenCookie(params: { token: string; token_expires_at: number }): Promise<void> {
  if (!canUseElectronSession()) return;
  const url = getAuthCookieUrl();
  await session.defaultSession.cookies.set({
    url,
    name: AUTH_TOKEN_COOKIE_NAME,
    value: params.token,
    httpOnly: true,
    secure: url.startsWith('https://'),
    sameSite: 'lax',
    expirationDate: params.token_expires_at / 1000,
  });
}

async function getTokenCookie(): Promise<{ token?: string; token_expires_at?: number }> {
  if (!canUseElectronSession()) return {};
  const url = getAuthCookieUrl();
  const cookies = await session.defaultSession.cookies.get({ url, name: AUTH_TOKEN_COOKIE_NAME });
  const first = Array.isArray(cookies) ? cookies[0] : undefined;
  if (!first || typeof first.value !== 'string') return {};
  const token_expires_at =
    typeof first.expirationDate === 'number' && Number.isFinite(first.expirationDate)
      ? first.expirationDate * 1000
      : undefined;
  return { token: first.value, token_expires_at };
}

async function clearTokenCookie(): Promise<void> {
  if (!canUseElectronSession()) return;
  const url = getAuthCookieUrl();
  await session.defaultSession.cookies.remove(url, AUTH_TOKEN_COOKIE_NAME);
}

async function readLocalToken(): Promise<{ token?: string; token_expires_at?: number | string }> {
  const cookie = await getTokenCookie().catch(() => ({
    token: undefined,
    token_expires_at: undefined,
  }));
  if (cookie.token) return cookie;
  const token = store.get('token');
  const token_expires_at = store.get('token_expires_at');
  return { token, token_expires_at };
}

/** 校验本地缓存 token 是否有效（中文注释）
 * 参数：params token 与过期时间戳（毫秒）
 * 返回：是否有效
 */
function isTokenValid(params: { token?: string; token_expires_at?: number | string }): boolean {
  if (!params.token) return false;
  const exp =
    typeof params.token_expires_at === 'number'
      ? params.token_expires_at
      : typeof params.token_expires_at === 'string'
        ? Number(params.token_expires_at)
        : NaN;
  if (!Number.isFinite(exp) || exp <= 0) return false;
  return Date.now() < exp;
}

/** 获取或创建当前设备 ID（中文注释）
 * 说明：用于单设备登录场景，服务端可基于 deviceId 踢下线旧会话
 * 返回：deviceId（持久化在 electron-store）
 */
function getOrCreateDeviceId(): string {
  const existing = store.get('device_id');
  if (typeof existing === 'string' && existing.trim()) return existing.trim();
  const id = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  store.set('device_id', id);
  return id;
}

/** 从登录接口返回中解析 token（中文注释）
 * 参数：payload 登录接口原始 JSON
 * 返回：解析结果（ok 为 true 表示 token 可用）
 */
export function pickTokenFromAuthPayload(payload: unknown): {
  token: string;
  token_expires_at?: number;
  username?: string;
  message?: string;
  ok: boolean;
} {
  if (!isPlainRecord(payload)) return { token: '', ok: false, message: '登录响应解析失败' };

  const success =
    typeof payload.success === 'boolean'
      ? payload.success
      : typeof payload.code === 'number'
        ? payload.code === 0
        : true;

  const message =
    typeof payload.message === 'string'
      ? payload.message
      : typeof payload.msg === 'string'
        ? payload.msg
        : '';

  const rawData = isPlainRecord(payload.data) ? payload.data : null;
  const token =
    (rawData &&
      (typeof rawData.token === 'string'
        ? rawData.token
        : typeof rawData.accessToken === 'string'
          ? rawData.accessToken
          : typeof rawData.access_token === 'string'
            ? rawData.access_token
            : '')) ||
    (typeof payload.token === 'string' ? payload.token : '') ||
    (typeof payload.accessToken === 'string' ? payload.accessToken : '') ||
    (typeof payload.access_token === 'string' ? payload.access_token : '');

  const expiresAtFromData =
    rawData &&
    typeof rawData.token_expires_at === 'number' &&
    Number.isFinite(rawData.token_expires_at)
      ? rawData.token_expires_at
      : rawData && typeof rawData.expiresAt === 'number' && Number.isFinite(rawData.expiresAt)
        ? rawData.expiresAt
        : undefined;
  const expiresInMsFromData =
    rawData && typeof rawData.expires_in === 'number' && Number.isFinite(rawData.expires_in)
      ? rawData.expires_in * 1000
      : rawData && typeof rawData.expiresIn === 'number' && Number.isFinite(rawData.expiresIn)
        ? rawData.expiresIn * 1000
        : undefined;
  const token_expires_at = expiresAtFromData
    ? expiresAtFromData
    : expiresInMsFromData
      ? Date.now() + expiresInMsFromData
      : undefined;

  const username =
    (rawData && isPlainRecord(rawData.user) && typeof rawData.user.username === 'string'
      ? rawData.user.username
      : rawData && typeof rawData.username === 'string'
        ? rawData.username
        : isPlainRecord(payload.user) && typeof payload.user.username === 'string'
          ? payload.user.username
          : undefined) || undefined;

  const ok = !!(success && token);
  return { token, token_expires_at, username, ok, message };
}

/** 判断校验接口返回是否表示“已失效”（中文注释）
 * 参数：params status HTTP 状态码；payload 接口返回 JSON
 * 返回：是否失效（true 表示应清理本地会话）
 */
export function isVerifyInvalid(params: { status: number; payload: unknown }): boolean {
  if (params.status === 401 || params.status === 403) return true;
  if (!isPlainRecord(params.payload)) return false;

  if (typeof params.payload.success === 'boolean') {
    return params.payload.success === false;
  }
  if (typeof params.payload.code === 'number') {
    return params.payload.code !== 0;
  }
  return false;
}

export function mockLogin(credentials: {
  username: string;
  password: string;
}): Promise<IBaseResponse<{ token: string }>> {
  if (credentials.username === 'test' && credentials.password === '123456') {
    const token = 'mock-token-' + Date.now();
    const token_expires_at = Date.now() + AUTH_TOKEN_TTL_MS;
    store.set('token', token);
    store.set('token_expires_at', token_expires_at);
    store.set('user', { username: 'test' });
    return Promise.resolve({ success: true, data: { token } });
  }
  return Promise.resolve({ success: false, message: '用户名或密码错误' });
}

/** 系统真实登录（中文注释）
 * 参数：credentials 用户名/密码（用户名按手机号传给服务端）
 * 返回：IBaseResponse<{token}>，成功时会把 token 落地到本地缓存
 */
export async function login(credentials: {
  username: string;
  password: string;
}): Promise<IBaseResponse<{ token: string }>> {
  try {
    const baseUrl = getAuthApiBaseUrl();
    const deviceId = getOrCreateDeviceId();
    const deviceName = `${os.hostname()}-${process.platform}`;
    const postData = {
      name: credentials.username,
      password: credentials.password,
      deviceId,
      deviceName,
    };
    console.log('login postData', postData);
    const res = await fetch(`${baseUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(postData),
    });

    const raw = (await res.json().catch(() => null)) as unknown;
    const parsed = pickTokenFromAuthPayload(raw);
    if (!res.ok && !parsed.ok) {
      return Promise.resolve({
        success: false,
        message: parsed.message || `登录失败（HTTP ${res.status}）`,
      });
    }
    if (!parsed.ok) {
      return Promise.resolve({ success: false, message: parsed.message || '登录失败' });
    }

    const token_expires_at =
      typeof parsed.token_expires_at === 'number' && Number.isFinite(parsed.token_expires_at)
        ? parsed.token_expires_at
        : Date.now() + AUTH_TOKEN_TTL_MS;

    store.set('token', parsed.token);
    store.set('token_expires_at', token_expires_at);
    store.set('user', { username: parsed.username || credentials.username });
    await setTokenCookie({ token: parsed.token, token_expires_at }).catch(() => void 0);

    return Promise.resolve({ success: true, data: { token: parsed.token } });
  } catch (e) {
    const errMsg = e instanceof Error ? e.message : String(e);
    return Promise.resolve({ success: false, message: errMsg || '登录失败' });
  }
}

/** 校验当前登录态是否仍有效（中文注释）
 * 说明：用于单设备登录场景，若服务端已踢下线则返回 valid=false 并清理本地 token
 * 返回：IBaseResponse<{valid}>
 */
export async function verifyAuth(): Promise<IBaseResponse<{ valid: boolean }>> {
  const { token, token_expires_at } = await readLocalToken();
  const ok = isTokenValid({ token, token_expires_at });
  if (!ok) {
    store.delete('token');
    store.delete('token_expires_at');
    store.delete('user');
    await clearTokenCookie().catch(() => void 0);
    return Promise.resolve({ success: true, data: { valid: false } });
  }

  if (typeof token === 'string' && token.startsWith('mock-token-')) {
    return Promise.resolve({ success: true, data: { valid: true } });
  }

  try {
    const baseUrl = getAuthApiBaseUrl();
    const res = await fetch(`${baseUrl}/auth/verify`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    const raw = (await res.json().catch(() => null)) as unknown;
    const invalid = isVerifyInvalid({ status: res.status, payload: raw });
    if (invalid) {
      store.delete('token');
      store.delete('token_expires_at');
      store.delete('user');
      await clearTokenCookie().catch(() => void 0);
      return Promise.resolve({ success: true, data: { valid: false }, message: '登录已失效' });
    }

    return Promise.resolve({ success: true, data: { valid: true } });
  } catch {
    return Promise.resolve({ success: true, data: { valid: true } });
  }
}

export function getStoredToken(): Promise<IBaseResponse<{ token?: string }>> {
  return verifyAuth()
    .then(async (r) => {
      if (!r.success) return { success: true, data: { token: undefined } };
      if (!r.data?.valid) return { success: true, data: { token: undefined }, message: r.message };
      const local = await readLocalToken();
      const ok = isTokenValid(local);
      return { success: true, data: { token: ok ? local.token : undefined } };
    })
    .catch(() => ({ success: true, data: { token: undefined } }));
}

export function clearSession(): Promise<IBaseResponse<boolean>> {
  store.delete('token');
  store.delete('token_expires_at');
  store.delete('user');
  return clearTokenCookie()
    .then(() => ({ success: true, data: true }))
    .catch(() => ({ success: true, data: true }));
}

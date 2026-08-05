// @vitest-environment jsdom
//
// 迴歸測試：鎖住上一輪修正的「路由參數變更不 remount、本地 state 沒重置」問題
// （買家填單成功畫面卡死、現場代填卡在已送出、後台殘留上一團的匯入草稿、分享頁殘留
// 「已複製連結」提示）。用 createMemoryRouter + 同一個 router 實例呼叫 navigate() 換參數，
// 而不是重新掛載 <MemoryRouter>，才會真的重現「同一元件實例、只是 params 變了」的情境。

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JoinPage } from './JoinPage';
import { OrderPage } from './OrderPage';
import { DashboardPage } from './DashboardPage';
import { SharePage } from './SharePage';
import { AppDataProvider } from '../AppData';
import type { GroupsApi } from '../hooks/useGroups';
import { encodeGroupPayload } from '../share/groupCodec';
import type { Group } from '../types';

function makeGroup(overrides: Partial<Group> = {}): Group {
  return {
    id: 'g1',
    name: '團 1',
    products: [{ id: 'p1', name: '珍奶', price: 60 }],
    orders: [],
    createdAt: 0,
    closed: false,
    ...overrides,
  };
}

/** 最小可用的 fake AppData：submitOrder 一律成功，其餘操作不影響本測試、留空即可。 */
function makeFakeAppData(groups: Group[]): GroupsApi {
  return {
    groups,
    loaded: true,
    storageError: null,
    dataCorrupted: false,
    addGroup: () => 'unused',
    removeGroup: () => {},
    toggleClosed: () => {},
    submitOrder: () => ({ ok: true }),
    togglePaid: () => {},
    removeOrder: () => {},
    dismissCorruptNotice: () => {},
  };
}

describe('JoinPage — 換一張團購單的填單連結（不同 d 參數）要重置回填單表單', () => {
  it('送出訂單卡在「訂單已送出」畫面後，換到另一團的連結要變回填單表單', async () => {
    const groupA = { id: 'ga', name: '團A', note: undefined, products: [{ id: 'p1', name: '雞排', price: 60 }] };
    const groupB = { id: 'gb', name: '團B', note: undefined, products: [{ id: 'p2', name: '珍奶', price: 50 }] };
    const dA = encodeGroupPayload(groupA);
    const dB = encodeGroupPayload(groupB);

    const router = createMemoryRouter(
      [{ path: '/join', element: <JoinPage /> }],
      { initialEntries: [`/join?d=${dA}`] },
    );
    render(<RouterProvider router={router} />);

    // 填單並送出。
    expect(screen.getByText('團A')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('你的名字'), { target: { value: '小明' } });
    fireEvent.click(screen.getByLabelText('增加 雞排'));
    fireEvent.click(screen.getByText('送出訂單'));

    // 卡在「訂單已送出」畫面（回單碼畫面）。
    await waitFor(() => expect(screen.getByText('訂單已送出')).toBeTruthy());
    expect(screen.queryByLabelText('你的名字')).toBeNull();

    // 換網址列到另一張團購單的連結（同一個 router、同一個 JoinPage 實例，只是 d 參數變了）。
    act(() => {
      router.navigate(`/join?d=${dB}`);
    });

    // 應該變回全新的填單表單，而不是卡在團A的「已送出」畫面。
    await waitFor(() => expect(screen.getByText('團B')).toBeTruthy());
    expect(screen.queryByText('訂單已送出')).toBeNull();
    expect(screen.getByLabelText('你的名字')).toHaveProperty('value', '');
  });
});

describe('OrderPage — 換團（:id 變）要重置「已送出」畫面與填單 state', () => {
  it('現場代填送出後卡在「已送出」，換去另一團要變回填單表單', async () => {
    const fakeApi = makeFakeAppData([makeGroup({ id: 'ga', name: '團A' }), makeGroup({ id: 'gb', name: '團B' })]);
    const router = createMemoryRouter(
      [
        {
          path: '/groups/:id/order',
          element: (
            <AppDataProvider value={fakeApi}>
              <OrderPage />
            </AppDataProvider>
          ),
        },
      ],
      { initialEntries: ['/groups/ga/order'] },
    );
    render(<RouterProvider router={router} />);

    await waitFor(() => expect(screen.getByText('團A')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('你的名字'), { target: { value: '小明' } });
    fireEvent.click(screen.getByLabelText('增加 珍奶'));
    fireEvent.click(screen.getByText('送出訂單'));

    await waitFor(() => expect(screen.getByText('已送出')).toBeTruthy());

    act(() => {
      router.navigate('/groups/gb/order');
    });

    await waitFor(() => expect(screen.getByText('團B')).toBeTruthy());
    expect(screen.queryByText('已送出')).toBeNull();
    expect(screen.getByLabelText('你的名字')).toHaveProperty('value', '');
  });
});

describe('DashboardPage — 換團（:id 變）要清掉上一團殘留的回單碼草稿 / 匯入訊息', () => {
  it('貼了錯誤回單碼觸發錯誤訊息後，換到另一團不該還看到上一團的錯誤訊息與草稿文字', async () => {
    const fakeApi = makeFakeAppData([makeGroup({ id: 'ga', name: '團A' }), makeGroup({ id: 'gb', name: '團B' })]);
    const router = createMemoryRouter(
      [
        {
          path: '/groups/:id',
          element: (
            <AppDataProvider value={fakeApi}>
              <DashboardPage />
            </AppDataProvider>
          ),
        },
      ],
      { initialEntries: ['/groups/ga'] },
    );
    render(<RouterProvider router={router} />);

    await waitFor(() => expect(screen.getByText('團A')).toBeTruthy());
    const textarea = screen.getByPlaceholderText(/把買家傳回的回單碼/);
    fireEvent.change(textarea, { target: { value: '這不是有效的回單碼' } });
    fireEvent.click(screen.getByText('匯入這張回單'));

    await waitFor(() => expect(screen.getByText(/讀不到有效的回單碼/)).toBeTruthy());

    act(() => {
      router.navigate('/groups/gb');
    });

    await waitFor(() => expect(screen.getByText('團B')).toBeTruthy());
    expect(screen.queryByText(/讀不到有效的回單碼/)).toBeNull();
    expect(screen.getByPlaceholderText(/把買家傳回的回單碼/)).toHaveProperty('value', '');
  });
});

describe('SharePage — 換團（:id 變）要清掉上一團殘留的「已複製連結」提示', () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it('複製過連結顯示「已複製連結 ✓」後，換到另一團要變回「複製連結」', async () => {
    const fakeApi = makeFakeAppData([makeGroup({ id: 'ga', name: '團A' }), makeGroup({ id: 'gb', name: '團B' })]);
    const router = createMemoryRouter(
      [
        {
          path: '/groups/:id/share',
          element: (
            <AppDataProvider value={fakeApi}>
              <SharePage />
            </AppDataProvider>
          ),
        },
      ],
      { initialEntries: ['/groups/ga/share'] },
    );
    render(<RouterProvider router={router} />);

    await waitFor(() => expect(screen.getByText('邀請填單')).toBeTruthy());
    fireEvent.click(screen.getByText('複製連結'));
    await waitFor(() => expect(screen.getByText('已複製連結 ✓')).toBeTruthy());

    act(() => {
      router.navigate('/groups/gb/share');
    });

    await waitFor(() => expect(screen.queryByText('已複製連結 ✓')).toBeNull());
    expect(screen.getByText('複製連結')).toBeTruthy();
  });
});

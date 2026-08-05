// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { JoinPage } from './JoinPage';
import { DashboardPage } from './DashboardPage';
import { AppDataProvider } from '../AppData';
import type { GroupsApi, SubmitOrderResult } from '../hooks/useGroups';
import { encodeGroupPayload } from '../share/groupCodec';
import { encodeReceipt } from '../share/receiptCodec';
import type { Group } from '../types';

describe('【實機發現 8】JoinPage — 已截止的團，步進器 +/− 與數量輸入要一起 disabled', () => {
  it('過了截止時間 → 減少/增加/數量輸入三顆控制項都 disabled（先前只有送出鍵被鎖）', () => {
    const def = {
      id: 'ga',
      name: '團A',
      products: [{ id: 'p1', name: '雞排', price: 60 }],
      deadlineAt: Date.now() - 60_000, // 一分鐘前就已截止
    };
    const d = encodeGroupPayload(def);
    render(
      <MemoryRouter initialEntries={[`/join?d=${d}`]}>
        <Routes>
          <Route path="/join" element={<JoinPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('這個團已截止，無法再填單。')).toBeTruthy();
    expect(screen.getByLabelText('減少 雞排')).toHaveProperty('disabled', true);
    expect(screen.getByLabelText('增加 雞排')).toHaveProperty('disabled', true);
    expect(screen.getByLabelText('雞排 數量')).toHaveProperty('disabled', true);
  });

  it('未截止 → 三顆控制項都可操作', () => {
    const def = {
      id: 'ga',
      name: '團A',
      products: [{ id: 'p1', name: '雞排', price: 60 }],
    };
    const d = encodeGroupPayload(def);
    render(
      <MemoryRouter initialEntries={[`/join?d=${d}`]}>
        <Routes>
          <Route path="/join" element={<JoinPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByLabelText('增加 雞排')).toHaveProperty('disabled', false);
    expect(screen.getByLabelText('雞排 數量')).toHaveProperty('disabled', false);
  });
});

describe('【Blocking 修正 3】買家備註：回單碼匯入後，主揪後台看得到（先前被靜默丟棄）', () => {
  function makeFakeAppData(groups: Group[], submitOrder: GroupsApi['submitOrder']): GroupsApi {
    return {
      groups,
      loaded: true,
      storageError: null,
      dataCorrupted: false,
      addGroup: () => 'unused',
      removeGroup: () => {},
      toggleClosed: () => {},
      submitOrder,
      togglePaid: () => {},
      removeOrder: () => {},
      dismissCorruptNotice: () => {},
    };
  }

  it('匯入含備註的回單碼後，逐人明細顯示「備註：...」', () => {
    const group: Group = {
      id: 'ga',
      name: '團A',
      products: [{ id: 'p1', name: '雞排', price: 60 }],
      orders: [],
      createdAt: 0,
      closed: false,
    };
    // 模擬 submitOrder 真的把 note 存進去（跟 useGroups.ts 的 applySubmitOrder 邏輯一致），
    // 這裡只需要驗證 DashboardPage 有把 parsed.note 傳進 submitOrder、並依更新後的 groups 顯示。
    let orders: Group['orders'] = [];
    const submitOrder = (
      _groupId: string,
      buyerName: string,
      items: Group['orders'][number]['items'],
      note?: string,
    ): SubmitOrderResult => {
      orders = [{ id: 'o1', buyerName, items, createdAt: 0, ...(note ? { note } : {}) }];
      group.orders = orders;
      return { ok: true };
    };
    const fakeApi = makeFakeAppData([group], submitOrder);

    const receipt = encodeReceipt({
      groupId: 'ga',
      buyerName: '小明',
      note: '不要辣',
      items: [{ productId: 'p1', qty: 1 }],
    });

    const { rerender } = render(
      <AppDataProvider value={fakeApi}>
        <MemoryRouter initialEntries={['/groups/ga']}>
          <Routes>
            <Route path="/groups/:id" element={<DashboardPage />} />
          </Routes>
        </MemoryRouter>
      </AppDataProvider>,
    );

    const textarea = screen.getByPlaceholderText(/把買家傳回的回單碼/);
    fireEvent.change(textarea, { target: { value: receipt } });
    fireEvent.click(screen.getByText('匯入這張回單'));

    // fake submitOrder 同步更新了 group.orders，但 groups 陣列參照本身沒變（跟真實 hook
    // 不同），所以手動 rerender 一次讓畫面拿到最新的 group.orders（等同「重新整理後看得到」）。
    rerender(
      <AppDataProvider value={fakeApi}>
        <MemoryRouter initialEntries={['/groups/ga']}>
          <Routes>
            <Route path="/groups/:id" element={<DashboardPage />} />
          </Routes>
        </MemoryRouter>
      </AppDataProvider>,
    );

    expect(screen.getByText('備註：不要辣')).toBeTruthy();
  });
});

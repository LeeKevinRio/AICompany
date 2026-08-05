// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { CreateGroupPage } from './CreateGroupPage';
import { AppDataProvider } from '../AppData';
import type { GroupsApi } from '../hooks/useGroups';
import { PRICE_INPUT_ERROR_MESSAGE } from '../priceInput';

function makeFakeAppData(addGroup: GroupsApi['addGroup']): GroupsApi {
  return {
    groups: [],
    loaded: true,
    storageError: null,
    dataCorrupted: false,
    addGroup,
    removeGroup: () => {},
    toggleClosed: () => {},
    submitOrder: () => ({ ok: true }),
    togglePaid: () => {},
    removeOrder: () => {},
    dismissCorruptNotice: () => {},
  };
}

function renderPage(addGroup: GroupsApi['addGroup']) {
  return render(
    <AppDataProvider value={makeFakeAppData(addGroup)}>
      <MemoryRouter initialEntries={['/new']}>
        <CreateGroupPage />
      </MemoryRouter>
    </AppDataProvider>,
  );
}

describe('【Major 修正】CreateGroupPage — 單價就地驗證，不再靜默 floor/clamp', () => {
  it('負數單價 → 顯示錯誤、擋下送出（不呼叫 addGroup）', () => {
    const addGroup = vi.fn<GroupsApi['addGroup']>(() => 'g1');
    renderPage(addGroup);

    fireEvent.change(screen.getByPlaceholderText('商品名稱'), { target: { value: '雞排' } });
    fireEvent.change(screen.getByPlaceholderText('單價'), { target: { value: '-5' } });

    expect(screen.getByText(PRICE_INPUT_ERROR_MESSAGE)).toBeTruthy();
    fireEvent.click(screen.getByText('建立團購'));
    expect(addGroup).not.toHaveBeenCalled();
  });

  it('小數單價 → 顯示錯誤、擋下送出', () => {
    const addGroup = vi.fn<GroupsApi['addGroup']>(() => 'g1');
    renderPage(addGroup);

    fireEvent.change(screen.getByPlaceholderText('商品名稱'), { target: { value: '雞排' } });
    fireEvent.change(screen.getByPlaceholderText('單價'), { target: { value: '12.5' } });

    expect(screen.getByText(PRICE_INPUT_ERROR_MESSAGE)).toBeTruthy();
    fireEvent.click(screen.getByText('建立團購'));
    expect(addGroup).not.toHaveBeenCalled();
  });

  it('合法單價（非負整數）→ 不顯示錯誤，送出時價格原樣送進 addGroup（不被 floor/clamp 改掉）', () => {
    const addGroup = vi.fn<GroupsApi['addGroup']>(() => 'g1');
    renderPage(addGroup);

    fireEvent.change(screen.getByPlaceholderText('商品名稱'), { target: { value: '雞排' } });
    fireEvent.change(screen.getByPlaceholderText('單價'), { target: { value: '60' } });

    expect(screen.queryByText(PRICE_INPUT_ERROR_MESSAGE)).toBeNull();
    fireEvent.click(screen.getByText('建立團購'));

    expect(addGroup).toHaveBeenCalledTimes(1);
    const [, , products] = addGroup.mock.calls[0];
    expect(products).toEqual([{ name: '雞排', price: 60 }]);
  });

  it('修正錯誤單價後錯誤訊息消失，可正常送出', () => {
    const addGroup = vi.fn<GroupsApi['addGroup']>(() => 'g1');
    renderPage(addGroup);

    const priceInput = screen.getByPlaceholderText('單價');
    fireEvent.change(screen.getByPlaceholderText('商品名稱'), { target: { value: '雞排' } });
    fireEvent.change(priceInput, { target: { value: '-5' } });
    expect(screen.getByText(PRICE_INPUT_ERROR_MESSAGE)).toBeTruthy();

    fireEvent.change(priceInput, { target: { value: '30' } });
    expect(screen.queryByText(PRICE_INPUT_ERROR_MESSAGE)).toBeNull();

    fireEvent.click(screen.getByText('建立團購'));
    expect(addGroup).toHaveBeenCalledTimes(1);
  });

  it('【QA 複審 non-blocking #3】超過位數上限的單價（8 位數）→ 顯示錯誤、擋下送出', () => {
    // 用 8 位數（剛好超過 MAX_PRICE_DIGITS=7 一位）驗證這條防線；純粹的「幾百位數字經
    // Number() 溢位成 Infinity」邏輯已在 priceInput.test.ts 用純函式測試直接覆蓋——
    // <input type="number"> 對超長數字字串本身有瀏覽器 / jsdom 層級的取值行為差異，不適合
    // 在這裡用幾百位數字重現，容易變成測 jsdom 的 number input 而不是測我們的驗證邏輯。
    const addGroup = vi.fn<GroupsApi['addGroup']>(() => 'g1');
    renderPage(addGroup);

    fireEvent.change(screen.getByPlaceholderText('商品名稱'), { target: { value: '雞排' } });
    fireEvent.change(screen.getByPlaceholderText('單價'), { target: { value: '99999999' } });

    expect(screen.getByText(PRICE_INPUT_ERROR_MESSAGE)).toBeTruthy();
    fireEvent.click(screen.getByText('建立團購'));
    expect(addGroup).not.toHaveBeenCalled();
  });
});

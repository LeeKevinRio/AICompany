import { describe, it, expect, vi } from 'vitest';
import { loadGroupsWithRecovery } from './useGroups';
import type { LoadResult, StorageRepository } from '../data/repository';
import type { Group } from '../types';

function makeGroup(id: string): Group {
  return {
    id,
    name: `團 ${id}`,
    products: [],
    orders: [],
    createdAt: 0,
    closed: false,
  };
}

/** 可注入 loadGroups 回傳值、並記錄 saveGroups 呼叫的假 repository。 */
function fakeRepo(loadResult: LoadResult): {
  repo: StorageRepository;
  saved: Group[][];
} {
  const saved: Group[][] = [];
  const repo: StorageRepository = {
    loadGroups: async () => loadResult,
    saveGroups: async (groups) => {
      saved.push(groups);
    },
  };
  return { repo, saved };
}

describe('loadGroupsWithRecovery', () => {
  it('毀損時把清理後的乾淨資料立即寫回（打破重複毀損警告迴圈）', async () => {
    const clean = [makeGroup('a')];
    const { repo, saved } = fakeRepo({ groups: clean, corrupted: true });
    const result = await loadGroupsWithRecovery(repo);

    expect(result.corrupted).toBe(true);
    expect(result.groups).toBe(clean);
    // 關鍵：毀損清理後必須寫回一次，且寫回的是清理後的乾淨資料。
    expect(saved).toHaveLength(1);
    expect(saved[0]).toBe(clean);
  });

  it('未毀損時不寫回（避免多餘寫入）', async () => {
    const { repo, saved } = fakeRepo({ groups: [makeGroup('a')], corrupted: false });
    await loadGroupsWithRecovery(repo);
    expect(saved).toHaveLength(0);
  });

  it('寫回失敗只記 log、不丟例外（仍回傳讀到的乾淨資料）', async () => {
    const clean = [makeGroup('a')];
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const repo: StorageRepository = {
      loadGroups: async () => ({ groups: clean, corrupted: true }),
      saveGroups: async () => {
        throw new Error('quota 滿');
      },
    };

    const result = await loadGroupsWithRecovery(repo);
    expect(result.groups).toBe(clean);
    expect(errSpy).toHaveBeenCalled();
    errSpy.mockRestore();
  });
});

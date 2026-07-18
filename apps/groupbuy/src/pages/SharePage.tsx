// 賣家分享頁：把團定義壓進連結，顯示可複製連結 + QR，供主揪貼到 LINE / 掃碼填單。
// 動線（方案 C）：主揪開完團 → 後台「邀請填單」→ 這頁 → 分享連結 → 買家從連結進填單頁。
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppData } from '../AppData';
import { buildShareUrl } from '../share/groupCodec';
import { QrCode } from '../components/QrCode';

export function SharePage() {
  const { id } = useParams<{ id: string }>();
  const { groups, loaded } = useAppData();
  const navigate = useNavigate();
  const [copied, setCopied] = useState(false);

  const group = groups.find((g) => g.id === id);

  // 用目前頁面的 origin + pathname 當 base，讓分享連結指回同一個部署位置。
  const shareUrl = useMemo(() => {
    if (!group) return '';
    const base =
      typeof window !== 'undefined'
        ? window.location.origin + window.location.pathname
        : '';
    return buildShareUrl(group, base);
  }, [group]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // 某些瀏覽器 / 非 https 下 clipboard 不可用：提示使用者手動複製。
      setCopied(false);
      alert('無法自動複製，請長按上方連結手動複製。');
    }
  }

  if (loaded && !group) {
    return (
      <div>
        <div className="page-header">
          <button className="back" onClick={() => navigate('/')} aria-label="返回">
            ‹
          </button>
          <h1>分享此團</h1>
        </div>
        <p className="empty">找不到這個團（可能已被刪除）。</p>
      </div>
    );
  }

  if (!group) return <p className="muted">載入中…</p>;

  return (
    <div>
      <div className="page-header">
        <button
          className="back"
          onClick={() => navigate(`/groups/${group.id}`)}
          aria-label="返回"
        >
          ‹
        </button>
        <h1>邀請填單</h1>
      </div>

      <p className="muted">
        把下面的連結貼到 LINE 群組，或讓對方掃 QR，就能直接填單——對方不需要安裝任何 app。
      </p>

      {group.closed && (
        <p className="banner warn">此團已截止：對方開啟連結後將無法送出訂單。</p>
      )}

      <div className="section-title">填單連結</div>
      <div className="card">
        <p className="share-link" style={{ wordBreak: 'break-all' }}>
          {shareUrl}
        </p>
        <button className="btn primary block" onClick={handleCopy}>
          {copied ? '已複製連結 ✓' : '複製連結'}
        </button>
      </div>

      <div className="section-title">掃碼填單</div>
      <div className="card" style={{ display: 'flex', justifyContent: 'center' }}>
        <QrCode value={shareUrl} cellSize={5} />
      </div>

      <p className="muted" style={{ fontSize: 13 }}>
        提示：買家填完會拿到一組「回單碼」，請他把回單碼貼回 LINE 給你，再到後台「貼上回單碼匯入」即可收單。
      </p>
    </div>
  );
}

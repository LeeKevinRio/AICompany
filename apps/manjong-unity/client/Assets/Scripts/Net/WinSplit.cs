using System.Collections.Generic;

namespace Manjong.Net
{
    /// <summary>
    /// Separates the winning tile from the winner's revealed hand so the UI can show it on its own.
    /// Pure logic (no Unity types) so it can be unit tested outside the engine.
    ///
    /// Steps (hand_end / game_end views, where the server reveals every hand and drawnTile is ""):
    /// 1. Only when view.hasResult, result.kind == "win", the player is result.winnerSeat and
    ///    result.winningTile is non-empty. Otherwise the hand is returned unchanged and WinningTile is "".
    /// 2. Flower wins (八仙過海 / 七搶一): the winning tile is a flower and never in the hand. The hand is left
    ///    alone; FlowerIndex is its position in player.flowers (or -1 when that player does not hold it, in which
    ///    case the UI shows it next to the flowers).
    /// 3. Otherwise, if drawnTile equals the winning tile (defensive: a live view), the drawn tile is the one.
    /// 4. Otherwise one copy is removed from the concealed hand, but only when the hand is a complete winning
    ///    shape, i.e. hand.Length == 17 - 3 * melds.Length (5 sets + pair; a kong still counts as one set).
    ///    That proves the winning tile is inside. If the server ever sends the hand without it (16 - 3m tiles),
    ///    nothing is removed, so a real tile of the same kind is never dropped. The winning tile is shown on its
    ///    own either way.
    /// </summary>
    public class WinSplit
    {
        /// <summary>Concealed tiles to show, in the given order, without the winning tile when it was removed.</summary>
        public List<string> Hand = new List<string>();
        /// <summary>The winning tile to show on its own; "" when this player did not win (or exhaustive draw).</summary>
        public string WinningTile = "";
        public bool SelfDraw;
        /// <summary>The winning tile is a flower (八仙過海 / 七搶一): mark it at the flowers, not at the hand.</summary>
        public bool IsFlowerWin;
        /// <summary>Index of the winning flower in player.flowers; -1 when not there.</summary>
        public int FlowerIndex = -1;
        /// <summary>True when one copy was taken out of the concealed hand.</summary>
        public bool RemovedFromHand;

        public bool HasWinningTile
        {
            get { return WinningTile.Length > 0; }
        }

        /// <param name="sortedHand">player.hand already sorted for display.</param>
        public static WinSplit For(GameView v, PlayerView p, List<string> sortedHand, bool isFlower)
        {
            var s = new WinSplit();
            if (sortedHand != null) s.Hand.AddRange(sortedHand);
            if (v == null || p == null || !v.hasResult || v.result == null) return s;
            HandResult r = v.result;
            if (r.kind != "win" || r.winnerSeat != p.seat || string.IsNullOrEmpty(r.winningTile)) return s;

            s.WinningTile = r.winningTile;
            s.SelfDraw = r.selfDraw;

            if (isFlower)
            {
                s.IsFlowerWin = true;
                string[] flowers = DtoUtil.Safe(p.flowers);
                for (int i = flowers.Length - 1; i >= 0; i--)
                {
                    if (flowers[i] == r.winningTile)
                    {
                        s.FlowerIndex = i;
                        break;
                    }
                }
                return s;
            }

            if (DtoUtil.Safe(p.drawnTile) == r.winningTile)
            {
                // The drawn tile is never part of "hand", so there is nothing to remove.
                s.RemovedFromHand = true;
                return s;
            }

            int melds = DtoUtil.Safe(p.melds).Length;
            int completeSize = 17 - 3 * melds;
            if (s.Hand.Count == completeSize)
            {
                int idx = s.Hand.LastIndexOf(r.winningTile);
                if (idx >= 0)
                {
                    s.Hand.RemoveAt(idx);
                    s.RemovedFromHand = true;
                }
            }
            return s;
        }
    }
}

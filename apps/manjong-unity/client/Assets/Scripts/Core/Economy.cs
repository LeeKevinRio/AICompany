namespace Manjong.Core
{
    /// <summary>
    /// Economy numbers shown in the UI. The server is authoritative; these are display / pre-check values only.
    /// MUST stay in sync with ECONOMY in apps/manjong-unity/server/src/engine/rules.ts.
    /// </summary>
    public static class Economy
    {
        /// <summary>ECONOMY.base: base payment per settlement.</summary>
        public const int BasePoints = 100;

        /// <summary>ECONOMY.perTai: payment per tai.</summary>
        public const int PerTai = 50;

        /// <summary>ECONOMY.minCoinsToPlay: below this a game cannot be started and relief can be claimed.</summary>
        public const int MinCoinsToPlay = 1000;

        /// <summary>ECONOMY.reliefAmount: relief tops the balance up to this amount.</summary>
        public const int ReliefAmount = 10000;
    }
}

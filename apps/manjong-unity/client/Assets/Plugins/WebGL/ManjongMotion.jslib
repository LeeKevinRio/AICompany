// WebGL-only bridge: tells the table UI whether the player's system asks for reduced motion
// (CSS media query prefers-reduced-motion: reduce). Returns 1 for "reduce", 0 otherwise or when the
// browser cannot answer.
mergeInto(LibraryManager.library, {
  ManjongPrefersReducedMotion: function () {
    try {
      return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 1 : 0;
    } catch (err) {
      return 0;
    }
  }
});

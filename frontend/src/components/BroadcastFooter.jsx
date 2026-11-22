import React from 'react';

export default function BroadcastFooter() {
  return (
    <footer 
      className="w-full max-w-7xl relative z-20 flex flex-wrap items-center justify-between gap-2 text-gray-300 text-xs px-4 py-1.5 bg-[#120826]/80 backdrop-blur border-t border-purple-800/40 rounded-sm mt-3"
      data-purpose="broadcast-footer"
    >
      <div className="flex items-center gap-2 font-rajdhani uppercase tracking-wider text-xs">
        <span className="text-amber-400 font-extrabold">GARENA FFWS OVERLAY ENGINE</span>
        <span className="text-purple-400">•</span>
        <span className="text-cyan-400">OFFICIAL TOURNAMENT DESKTOP BROADCAST FEED</span>
      </div>
      <div className="text-[11px] text-gray-400 font-rajdhani">
        Click on any team row to instantly award an elimination • Live auto-rank sort active
      </div>
    </footer>
  );
}


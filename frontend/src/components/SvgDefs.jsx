import React from 'react';

export default function SvgDefs() {
  return (
    <svg className="hidden" xmlns="http://www.w3.org/2000/svg">
      <defs>
        {/* Country Flags */}
        <g id="flag-mexico">
          <rect fill="#006847" height="18" rx="2" width="28" />
          <rect fill="#ffffff" height="18" width="9.33" x="9.33" />
          <rect fill="#ce1126" height="18" width="9.33" x="18.66" />
          <circle cx="14" cy="9" fill="#8b5e34" r="2.2" />
        </g>
        
        <g id="flag-indonesia">
          <rect fill="#ce1126" height="9" rx="1.5" width="28" />
          <rect fill="#ffffff" height="9" rx="1.5" width="28" y="9" />
        </g>
        
        <g id="flag-thailand">
          <rect fill="#ce1126" height="18" rx="2" width="28" />
          <rect fill="#ffffff" height="12" width="28" y="3" />
          <rect fill="#2d2a4a" height="6" width="28" y="6" />
        </g>
        
        <g id="flag-brazil">
          <rect fill="#009c3b" height="18" rx="2" width="28" />
          <polygon fill="#ffdf00" points="14,2 26,9 14,16 2,9" />
          <circle cx="14" cy="9" fill="#002776" r="4.2" />
        </g>
        
        <g id="flag-vietnam">
          <rect fill="#da251d" height="18" rx="2" width="28" />
          <polygon fill="#ff0" points="14,4 16.5,11.5 10,7 18,7 11.5,11.5" />
        </g>
        
        <g id="flag-morocco">
          <rect fill="#c1272d" height="18" rx="2" width="28" />
          <polygon fill="none" points="14,4.5 16,11 10.5,7 17.5,7 12,11" stroke="#006233" strokeWidth="1.2" />
        </g>

        {/* Esports Team Logos */}
        {/* 1. LYON */}
        <g id="logo-lyon">
          <circle cx="16" cy="16" fill="#1b1528" r="15" />
          <path d="M16 4 L20 10 L25 7 L23 15 L26 19 L19 21 L16 27 L13 21 L6 19 L9 15 L7 7 L12 10 Z" fill="#F6C33B" stroke="#997017" strokeWidth="0.8" />
          <circle cx="13" cy="14" fill="#1b1528" r="1.5" />
          <circle cx="19" cy="14" fill="#1b1528" r="1.5" />
        </g>

        {/* 2. ONIC */}
        <g id="logo-onic">
          <path d="M6 21 C6 21, 9 7, 18 6 C24 6, 27 10, 27 14 C27 20, 20 23, 15 23 L22 26 L12 26 Z" fill="#FFE500" />
          <polygon fill="#FFC400" points="14,10 11,5 17,8" />
          <polygon fill="#FFC400" points="9,14 5,11 11,12" />
          <circle cx="21" cy="12" fill="#150B28" r="1.8" />
        </g>

        {/* 3. AG */}
        <g id="logo-ag">
          <rect fill="#200d14" height="32" rx="4" width="32" />
          <path d="M6 25 L13 7 L19 7 L26 25 L20 25 L18 19 L14 19 L12 25 Z M15 15 L17 15 L16 11 Z" fill="#ED2128" />
          <text fill="#ffffff" fontFamily="'Barlow Condensed', sans-serif" fontSize="7" fontWeight="900" x="14" y="27">GLOBAL</text>
        </g>

        {/* 4. BRU */}
        <g id="logo-bru">
          <polygon fill="#ffffff" points="18,3 8,16 15,16 12,29 25,13 17,13" stroke="#0035ad" strokeWidth="1.2" />
        </g>

        {/* 5. FX */}
        <g id="logo-fx">
          <circle cx="16" cy="16" fill="#100b1a" r="15" stroke="#483366" strokeWidth="1.5" />
          <circle cx="16" cy="16" fill="none" r="13" stroke="#684a92" strokeDasharray="2,2" />
          <path d="M10 11 L22 21 M22 11 L10 21" stroke="#ffffff" strokeLinecap="round" strokeWidth="3.2" />
          <text fill="#9e8bb5" fontSize="5" fontWeight="bold" textAnchor="middle" x="16" y="29">FLUXO</text>
        </g>

        {/* 6. GOW */}
        <g id="logo-gow">
          <path d="M7 23 L9 13 L14 17 L21 7 L21 16 L26 18 L19 25 L14 22 Z" fill="#00D26A" />
          <path d="M14 17 L17 12 L19 16 Z" fill="#ffffff" />
          <path d="M10 24 C14 28, 22 28, 25 24" fill="none" stroke="#008a44" strokeWidth="2.5" />
        </g>

        {/* 7. LOS */}
        <g id="logo-los">
          <rect fill="#FF5500" height="22" rx="5" width="22" x="5" y="5" />
          <line stroke="#150B28" strokeWidth="4.5" x1="7" x2="25" y1="25" y2="7" />
          <circle cx="16" cy="16" fill="#ffffff" r="4" />
        </g>

        {/* 8. LOUD */}
        <g id="logo-loud">
          <polygon fill="none" points="6,25 16,7 26,25" stroke="#00FF66" strokeLinejoin="round" strokeWidth="3.5" />
          <rect fill="#0c173b" height="6" rx="2" width="22" x="5" y="25" />
          <text fill="#FF1744" fontSize="4.5" fontStyle="italic" fontWeight="900" textAnchor="middle" x="16" y="30">Snickers</text>
        </g>

        {/* 9. PE */}
        <g id="logo-pe">
          <circle cx="16" cy="16" fill="#1b122e" r="15" stroke="#5d4c82" strokeWidth="1.2" />
          <path d="M11 8 L19 8 C23 8, 24 11, 24 14 C24 17, 22 19, 19 19 L15 19 L15 25 L11 25 Z M15 12 L15 16 L18 16 C20 16, 20 12, 18 12 Z" fill="#ffffff" />
          <circle cx="16" cy="16" fill="none" r="13" stroke="#715d9a" strokeDasharray="1,3" />
        </g>

        {/* 10. RRQ */}
        <g id="logo-rrq">
          <path d="M7 23 L8 12 L12 16 L16 9 L20 16 L24 12 L25 23 Z" fill="#F6A800" />
          <path d="M10 23 L22 23 L20 25 L12 25 Z" fill="#B37400" />
          <circle cx="16" cy="8" fill="#FFEAA7" r="1.5" />
          <circle cx="8" cy="11" fill="#FFEAA7" r="1.2" />
          <circle cx="24" cy="11" fill="#FFEAA7" r="1.2" />
        </g>

        {/* 11. XP */}
        <g id="logo-xp">
          <polygon fill="#D8A528" points="6,6 12,6 26,26 20,26" />
          <polygon fill="#F6C33B" points="26,6 20,6 6,26 12,26" />
          <path d="M22 10 L27 10 L25 15 Z" fill="#F6C33B" />
          <path d="M5 21 L10 21 L8 16 Z" fill="#D8A528" />
        </g>

        {/* 12. FL */}
        <g id="logo-fl">
          <path d="M16 4 C18 11, 26 14, 26 21 C26 26, 21 28, 16 28 C10 28, 6 25, 6 19 C6 14, 10 11, 14 11 C14 14, 12 17, 15 19 C15 15, 17 9, 16 4 Z" fill="#FF5E00" />
          <path d="M16 16 C18 18, 19 20, 19 23 C19 25, 18 26, 16 26 C14 26, 13 25, 13 23 C13 20, 15 18, 16 16 Z" fill="#FFD000" />
        </g>
      </defs>
    </svg>
  );
}


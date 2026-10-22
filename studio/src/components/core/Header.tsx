import React from 'react';
import { GlobalHeader, type GlobalHeaderProps } from '../shell/GlobalHeader';

/**
 * Deprecation shim for legacy Header.tsx (Cosmic UI Phase 1, Refs #855, #856).
 * Re-exports the unified, token-based GlobalHeader.
 *
 * If ENABLE_LEGACY_HEADER environment flag is explicitly set, fallback logic
 * can be activated; otherwise defaults to GlobalHeader.
 */
export const Header: React.FC<GlobalHeaderProps & Record<string, unknown>> = (props) => {
  return <GlobalHeader {...props} />;
};

export default Header;

import React from 'react';
import { useLocation } from 'react-router-dom';
import { ChevronRight, Sun, Moon, Monitor } from 'lucide-react';

import { useTheme } from '../../hooks/useTheme';

const Header = () => {
    const location = useLocation();
    const { theme, cycleTheme } = useTheme();
    const pathSegments = location.pathname.split('/').filter(Boolean);

    const getBreadcrumbName = (segment: string) => {
        const map: Record<string, string> = {
            'partner-apps': 'Partner Apps',
            'api-keys': 'API Keys',
            'members': 'Members',
            'connections': 'Connections',
            'calls': 'Active Calls',
            'asterisk': 'Asterisk',
            'audit': 'Audit Events',
        };
        return map[segment] || segment.charAt(0).toUpperCase() + segment.slice(1);
    };

    return (
        <header className="h-14 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 flex items-center justify-between px-6 z-10 sticky top-0">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Control plane</span>
                {pathSegments.length > 0 && <ChevronRight className="w-4 h-4" />}
                {pathSegments.map((segment, index) => (
                    <React.Fragment key={segment}>
                        <span className={index === pathSegments.length - 1 ? 'font-medium text-foreground' : ''}>
                            {getBreadcrumbName(segment)}
                        </span>
                        {index < pathSegments.length - 1 && <ChevronRight className="w-4 h-4" />}
                    </React.Fragment>
                ))}
            </div>

            <div className="flex items-center gap-2">
                <button
                    type="button"
                    onClick={cycleTheme}
                    className="p-2 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors"
                    title={`Theme: ${theme} (click to cycle)`}
                    aria-label={`Current theme: ${theme}. Activate to cycle theme`}
                >
                    {theme === 'light' && <Sun className="w-4 h-4" />}
                    {theme === 'dark' && <Moon className="w-4 h-4" />}
                    {theme === 'system' && <Monitor className="w-4 h-4" />}
                </button>
            </div>
        </header>
    );
};

export default Header;

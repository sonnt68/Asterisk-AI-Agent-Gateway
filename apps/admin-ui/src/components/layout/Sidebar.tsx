import React from 'react';
import { NavLink } from 'react-router-dom';
import {
    LayoutDashboard,
    AppWindow,
    KeyRound,
    Radio,
    PhoneCall,
    Users,
    Server,
    ScrollText,
    ExternalLink,
    LogOut,
} from 'lucide-react';

import { useAuth } from '../../auth/AuthContext';

const SidebarItem = ({ to, icon: Icon, label, end = false }: { to: string, icon: any, label: string, end?: boolean }) => (
    <NavLink
        to={to}
        end={end}
        className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            }`
        }
    >
        <Icon className="w-4 h-4" />
        {label}
    </NavLink>
);

const SidebarGroup = ({ title, children }: { title: string, children: React.ReactNode }) => (
    <div className="mb-6">
        <h3 className="px-3 mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            {title}
        </h3>
        <div className="space-y-1">
            {children}
        </div>
    </div>
);

const Sidebar = () => {
    const { session, logout } = useAuth();

    return (
        <aside className="w-64 border-r border-border bg-card/50 backdrop-blur flex flex-col h-full">
            <div className="p-6 border-b border-border/50">
                <div className="flex items-center gap-3 font-bold text-xl tracking-tight">
                    <div className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                        <Radio className="w-6 h-6" />
                    </div>
                    <div className="flex flex-col leading-none">
                        <span>Gateway</span>
                        <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider mt-1">Asterisk AI Agent Gateway</span>
                    </div>
                </div>
            </div>

            <nav aria-label="Main navigation" className="flex-1 overflow-y-auto py-6 px-3">
                <SidebarGroup title="Overview">
                    <SidebarItem to="/" icon={LayoutDashboard} label="Dashboard" end />
                </SidebarGroup>

                <SidebarGroup title="Tenant Configuration">
                    <SidebarItem to="/partner-apps" icon={AppWindow} label="Partner Apps" />
                    <SidebarItem to="/api-keys" icon={KeyRound} label="API Keys" />
                    <SidebarItem to="/members" icon={Users} label="Members" />
                </SidebarGroup>

                <SidebarGroup title="Runtime">
                    <SidebarItem to="/connections" icon={Radio} label="Connections" />
                    <SidebarItem to="/calls" icon={PhoneCall} label="Active Calls" />
                    <SidebarItem to="/asterisk" icon={Server} label="Asterisk" />
                </SidebarGroup>

                <SidebarGroup title="Security">
                    <SidebarItem to="/audit" icon={ScrollText} label="Audit Events" />
                </SidebarGroup>

                <SidebarGroup title="Support">
                    <a
                        href="/api/v1/docs"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                    >
                        <ExternalLink className="w-4 h-4" />
                        API Docs
                    </a>
                </SidebarGroup>
            </nav>

            <div className="p-4 border-t border-border/50">
                <div className="flex items-center gap-3 px-2 mb-3">
                    <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-xs font-bold uppercase">
                        {session?.role?.substring(0, 2) || 'AD'}
                    </div>
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate capitalize">{session?.role || 'Member'}</p>
                        <p className="text-xs text-muted-foreground truncate" title={session?.organization_id}>
                            {session?.organization_id || 'No organization'}
                        </p>
                    </div>
                </div>
                <button
                    onClick={logout}
                    className="w-full flex items-center justify-center gap-2 px-2 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                    title="Logout"
                >
                    <LogOut className="w-3 h-3" />
                    Logout
                </button>
            </div>
        </aside>
    );
};

export default Sidebar;

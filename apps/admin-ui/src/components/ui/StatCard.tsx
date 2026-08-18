import React from 'react';
import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
    title: string;
    value: string | number;
    subValue?: string;
    icon: LucideIcon;
    color?: string;
}

export const StatCard = ({ title, value, subValue, icon: Icon, color = 'text-primary' }: StatCardProps) => (
    <div className="bg-card border border-border rounded-lg shadow-sm transition-all duration-200 hover:shadow-md hover:border-border/80">
        <div className="flex items-center gap-3 px-4 py-3">
            <Icon className={`w-5 h-5 ${color} flex-shrink-0`} />
            <div className="min-w-0">
                <div className="text-xs text-muted-foreground">{title}</div>
                <div className="text-lg font-bold">{value}</div>
                {subValue && <div className="text-[10px] text-muted-foreground truncate">{subValue}</div>}
            </div>
        </div>
    </div>
);

export default StatCard;

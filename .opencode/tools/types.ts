export interface LogEvent {
    type: string;
    message?: string;
    report?: string;
    [key: string]: unknown;
}

export interface Asset {
    id: string;
    price: number;
}

export interface Agent {
    id: string;
    wealth: number;
}

export interface StateEvent extends LogEvent {
    type: 'state';
    round: number;
    whale_wealth: number;
    assets: Asset[];
    agents: Agent[];
}

export interface LogEvent {
    type: string;
    message?: string;
    report?: string;
    agent_id?: string;
    session_id?: string;
    arena_dir?: string;
    api_url?: string;
    round?: number;
    whale_wealth?: number;
    assets?: Array<{ id: string; price: number }>;
    agents?: Array<{ id: string; wealth: number }>;
}

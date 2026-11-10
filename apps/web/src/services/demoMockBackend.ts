/**
 * Stateful In-Browser Demo Backend for Vercel / Static Deployments
 *
 * When the frontend is deployed to Vercel without a live FastAPI backend (or when
 * demo tokens `dev-token-*` are used against static hosting), this module serves
 * realistic, stateful responses backed by `localStorage` so all portals (Resident
 * Owner, Resident Tenant, Helpdesk Staff, Gate Security Tablet, and Managing
 * Committee) work end-to-end and share cross-portal state updates in real time.
 */

const STORAGE_KEY = 'isoswe_demo_state_v1';

const SOCIETY_ID = '11111111-1111-1111-1111-111111111111';
const TOWER_T07_ID = '22222222-2222-2222-2222-222222222207';
const TOWER_T12_ID = '22222222-2222-2222-2222-222222222212';
const TOWER_T21_ID = '22222222-2222-2222-2222-222222222221';

const FLAT_1203_ID = '33333333-3333-3333-3333-333333331203';
const FLAT_0408_ID = '33333333-3333-3333-3333-333333330408';
const FLAT_1601_ID = '33333333-3333-3333-3333-333333331601';

const GATE_1_ID = 'aaaaaaaa-1111-0000-0000-000000000001';

const USER_PROFILES: Record<string, any> = {
  'dev-token-neeraj': {
    user: {
      id: '44444444-4444-4444-4444-444444440001',
      supabase_uid: '00000000-0000-0000-0000-000000000001',
      email: 'neeraj.kulkarni@example.com',
      phone: '+91-98000-00001',
      full_name: 'Neeraj Kulkarni',
      status: 'ACTIVE',
    },
    roles: [{ society_id: SOCIETY_ID, role: 'RESIDENT' }],
    permissions: [],
    memberships: [
      {
        id: '55555555-5555-5555-5555-555555550001',
        society_id: SOCIETY_ID,
        flat_id: FLAT_1203_ID,
        flat_number: '1203',
        tower_id: TOWER_T07_ID,
        tower_number: 'T07',
        membership_type: 'OWNER',
        status: 'APPROVED',
        valid_from: '2026-01-01T00:00:00Z',
        valid_until: null,
        is_primary: true,
      },
    ],
  },
  'dev-token-swati': {
    user: {
      id: '44444444-4444-4444-4444-444444440002',
      supabase_uid: '00000000-0000-0000-0000-000000000002',
      email: 'swati.joshi@example.com',
      phone: '+91-98000-00002',
      full_name: 'Swati Joshi',
      status: 'ACTIVE',
    },
    roles: [{ society_id: SOCIETY_ID, role: 'RESIDENT' }],
    permissions: [],
    memberships: [
      {
        id: '55555555-5555-5555-5555-555555550002',
        society_id: SOCIETY_ID,
        flat_id: FLAT_0408_ID,
        flat_number: '0408',
        tower_id: TOWER_T12_ID,
        tower_number: 'T12',
        membership_type: 'TENANT',
        status: 'APPROVED',
        valid_from: '2026-06-01T00:00:00Z',
        valid_until: '2027-06-01T00:00:00Z',
        is_primary: true,
      },
    ],
  },
  'dev-token-aamir': {
    user: {
      id: '44444444-4444-4444-4444-444444440003',
      supabase_uid: '00000000-0000-0000-0000-000000000003',
      email: 'aamir.shaikh@example.com',
      phone: '+91-98000-00003',
      full_name: 'Aamir Shaikh',
      status: 'ACTIVE',
    },
    roles: [{ society_id: SOCIETY_ID, role: 'RESIDENT' }],
    permissions: [],
    memberships: [
      {
        id: '55555555-5555-5555-5555-555555550003',
        society_id: SOCIETY_ID,
        flat_id: FLAT_1601_ID,
        flat_number: '1601',
        tower_id: TOWER_T21_ID,
        tower_number: 'T21',
        membership_type: 'OWNER',
        status: 'APPROVED',
        valid_from: '2025-11-01T00:00:00Z',
        valid_until: null,
        is_primary: true,
      },
    ],
  },
  'dev-token-helpdesk': {
    user: {
      id: '44444444-4444-4444-4444-444444440004',
      supabase_uid: '00000000-0000-0000-0000-000000000004',
      email: 'helpdesk@example.com',
      phone: '+91-98000-00004',
      full_name: 'Rajesh Shinde',
      status: 'ACTIVE',
    },
    roles: [{ society_id: SOCIETY_ID, role: 'HELPDESK' }],
    permissions: [
      'COMPLAINT_MANAGE',
      'BANK_IMPORT',
      'RECONCILIATION_REVIEW',
      'BILLING_MANAGE',
      'GATE_OPERATIONS',
      'COMMUNICATIONS_MANAGE',
      'COMMITTEE_REPORT_READ',
    ],
    memberships: [],
  },
  'dev-token-gate': {
    user: {
      id: '44444444-4444-4444-4444-444444440004',
      supabase_uid: '00000000-0000-0000-0000-000000000004',
      email: 'gate.security@example.com',
      phone: '+91-98000-00004',
      full_name: 'Rajesh Shinde (Gate 1)',
      status: 'ACTIVE',
    },
    roles: [{ society_id: SOCIETY_ID, role: 'HELPDESK' }],
    permissions: ['GATE_OPERATIONS'],
    memberships: [],
  },
  'dev-token-committee': {
    user: {
      id: '44444444-4444-4444-4444-444444440006',
      supabase_uid: '00000000-0000-0000-0000-000000000006',
      email: 'committee@example.com',
      phone: '+91-98000-00006',
      full_name: 'Aniket Patwardhan',
      status: 'ACTIVE',
    },
    roles: [{ society_id: SOCIETY_ID, role: 'HELPDESK' }],
    permissions: ['COMMITTEE_REPORT_READ'],
    memberships: [],
  },
};

interface DemoState {
  flats: Record<string, any>;
  towers: any[];
  invoices: any[];
  payments: any[];
  amenities: any[];
  amenityBookings: any[];
  amenityBlocks: any[];
  notices: any[];
  notifications: any[];
  complaints: any[];
  visitors: any[];
  guestPasses: any[];
  residents: any[];
  upiMappings: any[];
}

function getInitialDemoState(): DemoState {
  const now = new Date().toISOString();
  const dueSoon = new Date(Date.now() + 7 * 86400000).toISOString();
  const overdue47 = new Date(Date.now() - 47 * 86400000).toISOString();
  const overdue18 = new Date(Date.now() - 18 * 86400000).toISOString();
  const currentPeriod = now.slice(0, 7);

  return {
    flats: {
      [FLAT_1203_ID]: {
        id: FLAT_1203_ID,
        society_id: SOCIETY_ID,
        tower_id: TOWER_T07_ID,
        tower_number: 'T07',
        tower_name: 'Tower 7',
        flat_number: '1203',
        area_sqft: 1150,
        status: 'OCCUPIED',
      },
      [FLAT_0408_ID]: {
        id: FLAT_0408_ID,
        society_id: SOCIETY_ID,
        tower_id: TOWER_T12_ID,
        tower_number: 'T12',
        tower_name: 'Tower 12',
        flat_number: '0408',
        area_sqft: 980,
        status: 'OCCUPIED',
      },
      [FLAT_1601_ID]: {
        id: FLAT_1601_ID,
        society_id: SOCIETY_ID,
        tower_id: TOWER_T21_ID,
        tower_number: 'T21',
        tower_name: 'Tower 21',
        flat_number: '1601',
        area_sqft: 1640,
        status: 'OCCUPIED',
      },
    },
    towers: [
      { id: TOWER_T07_ID, tower_number: 'T07', name: 'Tower 7' },
      { id: TOWER_T12_ID, tower_number: 'T12', name: 'Tower 12' },
      { id: TOWER_T21_ID, tower_number: 'T21', name: 'Tower 21' },
    ],
    invoices: [
      {
        id: '77777777-7777-7777-7777-777777770001',
        society_id: SOCIETY_ID,
        flat_id: FLAT_1203_ID,
        flat_number: '1203',
        tower_number: 'T07',
        invoice_number: `INV-${currentPeriod.replace('-', '')}-T07-1203`,
        billing_period: currentPeriod,
        area_sqft_snapshot: 1150,
        rate_paise_per_sqft_snapshot: 650,
        base_amount_paise: 747500,
        late_fee_paise: 0,
        total_paise: 747500,
        paid_paise: 0,
        balance_paise: 747500,
        currency: 'INR',
        status: 'UNPAID',
        issued_at: now,
        due_date: dueSoon,
        line_items: [
          {
            id: 'li-1',
            description: 'Monthly Maintenance Charges (1,150 sq ft @ ₹6.50/sq ft)',
            amount_paise: 747500,
          },
        ],
      },
      {
        id: '77777777-7777-7777-7777-777777770002',
        society_id: SOCIETY_ID,
        flat_id: FLAT_0408_ID,
        flat_number: '0408',
        tower_number: 'T12',
        invoice_number: 'INV-202609-T12-0408',
        billing_period: '2026-09',
        area_sqft_snapshot: 980,
        rate_paise_per_sqft_snapshot: 650,
        base_amount_paise: 637000,
        late_fee_paise: 0,
        total_paise: 637000,
        paid_paise: 0,
        balance_paise: 637000,
        currency: 'INR',
        status: 'OVERDUE',
        issued_at: overdue47,
        due_date: overdue47,
        line_items: [
          {
            id: 'li-2',
            description: 'Monthly Maintenance Charges (980 sq ft @ ₹6.50/sq ft)',
            amount_paise: 637000,
          },
        ],
      },
      {
        id: '77777777-7777-7777-7777-777777770003',
        society_id: SOCIETY_ID,
        flat_id: FLAT_1601_ID,
        flat_number: '1601',
        tower_number: 'T21',
        invoice_number: 'INV-202610-T21-1601',
        billing_period: '2026-10',
        area_sqft_snapshot: 1640,
        rate_paise_per_sqft_snapshot: 650,
        base_amount_paise: 1066000,
        late_fee_paise: 0,
        total_paise: 1066000,
        paid_paise: 500000,
        balance_paise: 566000,
        currency: 'INR',
        status: 'PARTIALLY_PAID',
        issued_at: overdue18,
        due_date: overdue18,
        line_items: [
          {
            id: 'li-3',
            description: 'Monthly Maintenance Charges (1,640 sq ft @ ₹6.50/sq ft)',
            amount_paise: 1066000,
          },
        ],
      },
    ],
    payments: [
      {
        id: '88888888-8888-8888-8888-888888880001',
        society_id: SOCIETY_ID,
        flat_id: FLAT_1601_ID,
        invoice_id: '77777777-7777-7777-7777-777777770003',
        user_id: '44444444-4444-4444-4444-444444440003',
        amount_paise: 500000,
        currency: 'INR',
        status: 'SUCCEEDED',
        provider_name: 'razorpay_upi',
        provider_payment_id: 'pay_DemoAamir5000',
        receipt_number: 'RCP-202610-0001',
        paid_at: overdue18,
        created_at: overdue18,
      },
    ],
    amenities: [
      {
        id: 'bbbbbbbb-1111-0000-0000-000000000001',
        society_id: SOCIETY_ID,
        name: 'Grand Clubhouse Banquet',
        amenity_type: 'CLUBHOUSE',
        description: 'Air-conditioned multipurpose banquet hall for resident gatherings.',
        guidelines: 'Book at least 24 hours in advance. Security deposit applicable.',
        location: 'Central Clubhouse - Ground Floor',
        capacity: 50,
        slot_duration_minutes: 120,
        opening_time: '08:00',
        closing_time: '22:00',
        booking_fee_paise: 150000,
        advance_booking_days: 30,
        min_advance_hours: 2,
        max_slots_per_day_per_resident: 2,
        cancellation_deadline_hours: 12,
        refund_percentage: 80,
        allowed_membership_types: ['OWNER', 'TENANT'],
        is_active: true,
        created_at: now,
        updated_at: now,
      },
      {
        id: 'bbbbbbbb-2222-0000-0000-000000000002',
        society_id: SOCIETY_ID,
        name: 'Indoor Badminton Court 1',
        amenity_type: 'BADMINTON_COURT',
        description: 'BWF-grade synthetic indoor badminton court with LED lighting.',
        guidelines: 'Non-marking shoes mandatory.',
        location: 'Sports Complex - Level 1',
        capacity: 4,
        slot_duration_minutes: 60,
        opening_time: '06:00',
        closing_time: '22:00',
        booking_fee_paise: 20000,
        advance_booking_days: 7,
        min_advance_hours: 1,
        max_slots_per_day_per_resident: 2,
        cancellation_deadline_hours: 4,
        refund_percentage: 100,
        allowed_membership_types: ['OWNER', 'TENANT'],
        is_active: true,
        created_at: now,
        updated_at: now,
      },
      {
        id: 'bbbbbbbb-3333-0000-0000-000000000003',
        society_id: SOCIETY_ID,
        name: 'Floodlit Tennis Court',
        amenity_type: 'TENNIS_COURT',
        description: 'Championship hard-court surface with evening floodlights.',
        guidelines: 'Bring your own racquets and tennis balls.',
        location: 'North Sports Arena',
        capacity: 4,
        slot_duration_minutes: 60,
        opening_time: '06:00',
        closing_time: '21:00',
        booking_fee_paise: 30000,
        advance_booking_days: 7,
        min_advance_hours: 1,
        max_slots_per_day_per_resident: 2,
        cancellation_deadline_hours: 4,
        refund_percentage: 80,
        allowed_membership_types: ['OWNER', 'TENANT'],
        is_active: true,
        created_at: now,
        updated_at: now,
      },
      {
        id: 'bbbbbbbb-4444-0000-0000-000000000004',
        society_id: SOCIETY_ID,
        name: 'Infinity Swimming Pool & Deck',
        amenity_type: 'SWIMMING_POOL',
        description: 'Temperature-controlled 25m lap pool with lifeguard on duty.',
        guidelines: 'Proper swimwear and shower before entry mandatory.',
        location: 'Clubhouse Podium',
        capacity: 20,
        slot_duration_minutes: 60,
        opening_time: '06:00',
        closing_time: '20:00',
        booking_fee_paise: 0,
        advance_booking_days: 7,
        min_advance_hours: 1,
        max_slots_per_day_per_resident: 2,
        cancellation_deadline_hours: 2,
        refund_percentage: 100,
        allowed_membership_types: ['OWNER', 'TENANT'],
        is_active: true,
        created_at: now,
        updated_at: now,
      },
    ],
    amenityBookings: [] as any[],
    amenityBlocks: [] as any[],
    notices: [
      {
        id: 'notice-demo-1',
        society_id: SOCIETY_ID,
        title: 'Quarterly Water Tank Cleaning & Chlorination Schedule',
        body: 'Overhead and underground domestic water tanks across Towers T01–T28 will undergo scheduled high-pressure cleaning and UV chlorination this Saturday between 10:00 AM and 2:00 PM IST. Please store adequate water in advance.',
        category: 'MAINTENANCE',
        priority: 'HIGH',
        status: 'PUBLISHED',
        target_type: 'SOCIETY',
        target_tower_id: null,
        target_flat_id: null,
        target_tower_ids: [],
        target_flat_ids: [],
        is_pinned: true,
        is_emergency: false,
        version: 1,
        published_at: now,
        expires_at: null,
        scheduled_publish_at: null,
        created_by: '44444444-4444-4444-4444-444444440004',
        author_name: 'Rajesh Shinde',
        is_read: false,
        read_at: null,
        read_count: 14,
        created_at: now,
        updated_at: now,
      },
      {
        id: 'notice-demo-2',
        society_id: SOCIETY_ID,
        title: 'Annual General Body Meeting (AGM) — FY 2026-27',
        body: 'All flat owners of Marvel Greenfield Residences are invited to attend the Annual General Body Meeting at the Grand Clubhouse Banquet on Sunday at 11:00 AM IST. Agenda includes audited financials, solar rooftop phase-2, and EV charging bays.',
        category: 'EVENT',
        priority: 'NORMAL',
        status: 'PUBLISHED',
        target_type: 'SOCIETY',
        target_tower_id: null,
        target_flat_id: null,
        target_tower_ids: [],
        target_flat_ids: [],
        is_pinned: false,
        is_emergency: false,
        version: 1,
        published_at: now,
        expires_at: null,
        scheduled_publish_at: null,
        created_by: '44444444-4444-4444-4444-444444440006',
        author_name: 'Aniket Patwardhan',
        is_read: false,
        read_at: null,
        read_count: 42,
        created_at: now,
        updated_at: now,
      },
    ],
    notifications: [
      {
        id: 'notif-demo-1',
        society_id: SOCIETY_ID,
        recipient_user_id: '44444444-4444-4444-4444-444444440001',
        title: 'Official Notice: Quarterly Water Tank Cleaning',
        body: 'Scheduled tank cleaning this Saturday from 10:00 AM to 2:00 PM IST.',
        event_type: 'notice.published',
        priority: 'HIGH',
        aggregate_type: 'notice',
        aggregate_id: 'notice-demo-1',
        deep_link: '/resident/notices',
        is_read: false,
        read_at: null,
        created_at: now,
      },
    ],
    complaints: [
      {
        id: 'cmp-demo-1',
        society_id: SOCIETY_ID,
        flat_id: FLAT_1203_ID,
        flat_number: '1203',
        tower_number: 'T07',
        complaint_number: 'CMP-202611-0001',
        title: 'Low water pressure in master bathroom line',
        description: 'Water pressure in the master bedroom shower has dropped significantly over the last 2 days.',
        category: 'PLUMBING',
        priority: 'MEDIUM',
        status: 'IN_PROGRESS',
        created_by: '44444444-4444-4444-4444-444444440001',
        creator_name: 'Neeraj Kulkarni',
        assigned_to: '44444444-4444-4444-4444-444444440004',
        assignee_name: 'Rajesh Shinde',
        safety_escalated: false,
        safety_escalation_reason: null,
        ai_status: 'COMPLETED',
        ai_suggested_category: 'PLUMBING',
        ai_confidence: 0.94,
        is_sla_breached: false,
        first_response_sla_breached: false,
        first_response_deadline: dueSoon,
        resolution_deadline: dueSoon,
        first_response_at: now,
        resolved_at: null,
        closed_at: null,
        reopened_count: 0,
        rating: null,
        feedback: null,
        duplicate_of_id: null,
        duplicate_candidates: [],
        comments: [
          {
            id: 'comm-1',
            complaint_id: 'cmp-demo-1',
            user_id: '44444444-4444-4444-4444-444444440004',
            user_name: 'Rajesh Shinde',
            user_role: 'HELPDESK',
            comment: 'Plumbing technician has inspected the PRV valve on the 12th floor shaft and is replacing the cartridge.',
            is_internal: false,
            created_at: now,
          },
        ],
        attachments: [],
        activities: [
          {
            id: 'act-1',
            activity_type: 'STATUS_CHANGED',
            old_value: 'SUBMITTED',
            new_value: 'IN_PROGRESS',
            actor_name: 'Rajesh Shinde',
            notes: 'Assigned to plumbing maintenance team',
            created_at: now,
          },
        ],
        created_at: now,
        updated_at: now,
      },
    ],
    visitors: [
      {
        id: 'vis-demo-1',
        society_id: SOCIETY_ID,
        gate_id: GATE_1_ID,
        gate_name: 'Gate 1 - North Main',
        destination_flat_id: FLAT_1203_ID,
        flat_number: '1203',
        tower_number: 'T07',
        visitor_name: 'Ramesh Delivery (BlueDart)',
        phone_number: '+919822011223',
        masked_phone: '+91-XXXXXX1223',
        vehicle_number: 'MH-12-AB-4501',
        purpose: 'DELIVERY',
        approval_status: 'PENDING',
        entry_status: 'EXPECTED',
        entry_time: null,
        exit_time: null,
        created_at: now,
        updated_at: now,
      },
    ],
    guestPasses: [
      {
        pass_id: 'gp-demo-1',
        id: 'gp-demo-1',
        society_id: SOCIETY_ID,
        destination_flat_id: FLAT_1203_ID,
        flat_number: '1203',
        tower_number: 'T07',
        guest_name: 'Dr. Vivek Deshmukh',
        guest_phone: '+919850011223',
        purpose: 'Family Visit',
        pass_type: 'SINGLE_USE',
        pass_code_prefix: 'GP-',
        pass_code: 'GP-K7M2-9QXA-V4RB',
        status: 'ACTIVE',
        max_uses: 1,
        used_count: 0,
        valid_from: now,
        valid_until: dueSoon,
        created_at: now,
      },
    ],
    residents: [
      {
        user_id: '44444444-4444-4444-4444-444444440001',
        full_name: 'Neeraj Kulkarni',
        email: 'neeraj.kulkarni@example.com',
        phone: '+91-98000-00001',
        status: 'ACTIVE',
        user_status: 'ACTIVE',
        flats: [
          {
            membership_id: '55555555-5555-5555-5555-555555550001',
            flat_id: FLAT_1203_ID,
            flat_number: '1203',
            tower_id: TOWER_T07_ID,
            tower_number: 'T07',
            membership_type: 'OWNER',
            status: 'APPROVED',
            membership_status: 'APPROVED',
            valid_from: '2026-01-01T00:00:00Z',
            valid_until: null,
            is_primary: true,
          },
        ],
      },
      {
        user_id: '44444444-4444-4444-4444-444444440002',
        full_name: 'Swati Joshi',
        email: 'swati.joshi@example.com',
        phone: '+91-98000-00002',
        status: 'ACTIVE',
        user_status: 'ACTIVE',
        flats: [
          {
            membership_id: '55555555-5555-5555-5555-555555550002',
            flat_id: FLAT_0408_ID,
            flat_number: '0408',
            tower_id: TOWER_T12_ID,
            tower_number: 'T12',
            membership_type: 'TENANT',
            status: 'APPROVED',
            membership_status: 'APPROVED',
            valid_from: '2026-06-01T00:00:00Z',
            valid_until: '2027-06-01T00:00:00Z',
            is_primary: true,
          },
        ],
      },
      {
        user_id: '44444444-4444-4444-4444-444444440003',
        full_name: 'Aamir Shaikh',
        email: 'aamir.shaikh@example.com',
        phone: '+91-98000-00003',
        status: 'ACTIVE',
        user_status: 'ACTIVE',
        flats: [
          {
            membership_id: '55555555-5555-5555-5555-555555550003',
            flat_id: FLAT_1601_ID,
            flat_number: '1601',
            tower_id: TOWER_T21_ID,
            tower_number: 'T21',
            membership_type: 'OWNER',
            status: 'APPROVED',
            membership_status: 'APPROVED',
            valid_from: '2025-11-01T00:00:00Z',
            valid_until: null,
            is_primary: true,
          },
        ],
      },
    ],
    upiMappings: [
      {
        id: 'upi-demo-1',
        society_id: SOCIETY_ID,
        flat_id: FLAT_1203_ID,
        flat_number: '1203',
        tower_number: 'T07',
        vpa: 'neeraj.kulkarni@okicici',
        user_id: '44444444-4444-4444-4444-444444440001',
        resident_name: 'Neeraj Kulkarni',
        is_verified: true,
        notes: 'Primary owner UPI handle',
        created_at: now,
      },
    ],
  };
}

function loadState(): DemoState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return { ...getInitialDemoState(), ...JSON.parse(raw) };
    }
  } catch {
    // Ignore storage read errors
  }
  const initial = getInitialDemoState();
  saveState(initial);
  return initial;
}

function saveState(state: DemoState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignore storage write errors
  }
}

function parseBody(options?: RequestInit): any {
  if (!options?.body || typeof options.body !== 'string') return {};
  try {
    return JSON.parse(options.body);
  } catch {
    return {};
  }
}

export function handleDemoApiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
  token: string
): T {
  const method = (options.method || 'GET').toUpperCase();
  const [pathOnly, queryString = ''] = endpoint.split('?');
  const params = new URLSearchParams(queryString);
  const profile = USER_PROFILES[token] || USER_PROFILES['dev-token-neeraj'];
  const activeFlatId = profile.memberships?.[0]?.flat_id || FLAT_1203_ID;
  const state = loadState();
  const now = new Date().toISOString();

  // 1. Auth profile (/api/v1/me)
  if (pathOnly === '/api/v1/me') {
    return profile as unknown as T;
  }

  // 2. Health & Staff Overview probes
  if (pathOnly === '/health/live' || pathOnly === '/health/ready') {
    return {
      status: 'healthy',
      uptime_seconds: 86420,
      database: 'connected (demo)',
      version: '1.0.0',
    } as unknown as T;
  }
  if (pathOnly === '/api/v1/events/health-check-event' && method === 'POST') {
    return {
      message: 'Health check event committed to transactional outbox',
      outbox_event_id: 'evt-' + Math.random().toString(36).slice(2, 10),
    } as unknown as T;
  }
  if (pathOnly === '/api/v1/finance/batch-billing/preview' && method === 'POST') {
    return {
      status: 'AUTHORIZED',
      message: 'RBAC Verified: Staff user authorized for batch billing & financial reconciliation.',
    } as unknown as T;
  }

  // 3. Flats (/api/v1/flats/:id)
  if (pathOnly.startsWith('/api/v1/flats/')) {
    const flatId = pathOnly.split('/').pop() || FLAT_1203_ID;
    return (state.flats[flatId] || state.flats[FLAT_1203_ID]) as unknown as T;
  }

  // 4. Billing & Payments
  if (pathOnly === '/api/v1/billing/me/summary') {
    const myInvoices = state.invoices.filter((i: any) => i.flat_id === activeFlatId);
    const totalOutstanding = myInvoices.reduce((acc: number, i: any) => acc + i.balance_paise, 0);
    const overdueCount = myInvoices.filter((i: any) => i.status === 'OVERDUE').length;
    return {
      flat_id: activeFlatId,
      total_outstanding_paise: totalOutstanding,
      overdue_invoices_count: overdueCount,
      unpaid_invoices_count: myInvoices.filter((i: any) => i.balance_paise > 0).length,
      last_payment_date: state.payments[0]?.paid_at || null,
      last_payment_amount_paise: state.payments[0]?.amount_paise || 0,
      currency: 'INR',
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/billing/me/invoices') {
    const statusFilter = params.get('status');
    let list = state.invoices.filter((i: any) => i.flat_id === activeFlatId);
    if (statusFilter) {
      list = list.filter((i: any) => i.status === statusFilter);
    }
    return list as unknown as T;
  }

  if (pathOnly === '/api/v1/billing/me/payments') {
    return state.payments.filter((p: any) => p.flat_id === activeFlatId) as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/billing\/invoices\/[^/]+\/payments$/) && method === 'POST') {
    const parts = pathOnly.split('/');
    const invoiceId = parts[parts.length - 2];
    const body = parseBody(options);
    const inv = state.invoices.find((i: any) => i.id === invoiceId) || state.invoices[0];
    const amount = Number(body.amount_paise || inv.balance_paise);
    inv.paid_paise = (inv.paid_paise || 0) + amount;
    inv.balance_paise = Math.max(0, inv.total_paise - inv.paid_paise);
    inv.status = inv.balance_paise === 0 ? 'PAID' : 'PARTIALLY_PAID';
    const payment = {
      id: 'pay-' + Date.now(),
      society_id: SOCIETY_ID,
      flat_id: inv.flat_id,
      invoice_id: inv.id,
      user_id: profile.user.id,
      amount_paise: amount,
      currency: 'INR',
      status: 'SUCCEEDED',
      provider_name: 'razorpay_upi',
      provider_payment_id: 'pay_Demo' + Math.floor(Math.random() * 100000),
      receipt_number: `RCP-${new Date().toISOString().slice(0, 7).replace('-', '')}-${state.payments.length + 1}`,
      paid_at: now,
      created_at: now,
    };
    state.payments.unshift(payment);
    saveState(state);
    return payment as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/billing\/invoices\/[^/]+\/receipt$/)) {
    const parts = pathOnly.split('/');
    const invoiceId = parts[parts.length - 2];
    const inv = state.invoices.find((i: any) => i.id === invoiceId) || state.invoices[0];
    return {
      invoice_id: inv.id,
      invoice_number: inv.invoice_number,
      receipt_number: `RCP-${inv.billing_period.replace('-', '')}-001`,
      society_name: 'Marvel Greenfield Residences',
      flat_number: inv.flat_number,
      tower_number: inv.tower_number,
      billing_period: inv.billing_period,
      total_paise: inv.total_paise,
      paid_paise: inv.paid_paise,
      balance_paise: inv.balance_paise,
      status: inv.status,
      issued_at: inv.issued_at,
      payments: state.payments.filter((p: any) => p.invoice_id === inv.id),
    } as unknown as T;
  }

  if (pathOnly.startsWith('/api/v1/billing/invoices/')) {
    const invoiceId = pathOnly.split('/').pop();
    return (state.invoices.find((i: any) => i.id === invoiceId) || state.invoices[0]) as unknown as T;
  }

  if (pathOnly === '/api/v1/billing/staff/overview') {
    const totalBilled = state.invoices.reduce((s: number, i: any) => s + i.total_paise, 0);
    const totalPaid = state.invoices.reduce((s: number, i: any) => s + i.paid_paise, 0);
    return {
      society_id: SOCIETY_ID,
      total_invoices_count: state.invoices.length,
      total_billed_paise: totalBilled,
      total_collected_paise: totalPaid,
      total_outstanding_paise: totalBilled - totalPaid,
      paid_count: state.invoices.filter((i: any) => i.status === 'PAID').length,
      unpaid_count: state.invoices.filter((i: any) => i.status === 'UNPAID').length,
      overdue_count: state.invoices.filter((i: any) => i.status === 'OVERDUE').length,
      partially_paid_count: state.invoices.filter((i: any) => i.status === 'PARTIALLY_PAID').length,
      currency: 'INR',
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/billing/staff/invoices') {
    return state.invoices as unknown as T;
  }

  if (pathOnly === '/api/v1/billing/late-fee-policies') {
    return [
      {
        id: 'lfp-1',
        society_id: SOCIETY_ID,
        policy_name: 'Standard 18% p.a. Monthly Simple Interest',
        calculation_method: 'PERCENTAGE_PER_MONTH',
        amount_or_rate_bps: 150,
        grace_period_days: 15,
        min_charge_paise: 10000,
        max_charge_paise: 500000,
        is_active: true,
        effective_from: '2026-01-01T00:00:00Z',
      },
    ] as unknown as T;
  }

  if (pathOnly === '/api/v1/billing/late-fees/preview') {
    return {
      policy: null,
      evaluated_at: now,
      total_eligible_invoices: 1,
      total_proposed_fee_paise: 9555,
      items: [
        {
          invoice_id: '77777777-7777-7777-7777-777777770002',
          invoice_number: 'INV-202609-T12-0408',
          flat_number: '0408',
          tower_number: 'T12',
          billing_period: '2026-09',
          due_date: state.invoices[1].due_date,
          days_overdue: 47,
          unpaid_principal_paise: 637000,
          proposed_fee_paise: 9555,
          explanation: '1.5% monthly interest on ₹6,370.00 (47 days overdue)',
        },
      ],
    } as unknown as T;
  }

  // 5. Amenities
  if (pathOnly === '/api/v1/amenities' && method === 'GET') {
    const typeFilter = params.get('amenity_type');
    let items = state.amenities;
    if (typeFilter) {
      items = items.filter((a: any) => a.amenity_type === typeFilter);
    }
    return { items, total: items.length } as unknown as T;
  }

  if (pathOnly === '/api/v1/amenities/staff' && method === 'POST') {
    const body = parseBody(options);
    const created = {
      id: 'amn-' + Date.now(),
      society_id: SOCIETY_ID,
      name: body.name || 'New Township Amenity',
      amenity_type: body.amenity_type || 'CLUBHOUSE',
      description: body.description || '',
      guidelines: body.guidelines || '',
      location: body.location || 'Main Clubhouse',
      capacity: body.capacity ?? 10,
      slot_duration_minutes: body.slot_duration_minutes ?? 60,
      opening_time: body.opening_time || '06:00',
      closing_time: body.closing_time || '22:00',
      booking_fee_paise: body.booking_fee_paise ?? 0,
      advance_booking_days: body.advance_booking_days ?? 7,
      min_advance_hours: body.min_advance_hours ?? 1,
      max_slots_per_day_per_resident: body.max_slots_per_day_per_resident ?? 2,
      cancellation_deadline_hours: body.cancellation_deadline_hours ?? 4,
      refund_percentage: body.refund_percentage ?? 80,
      allowed_membership_types: body.allowed_membership_types || ['OWNER', 'TENANT'],
      is_active: true,
      created_at: now,
      updated_at: now,
    };
    state.amenities.unshift(created);
    saveState(state);
    return created as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/amenities\/staff\/[^/]+\/status$/) && method === 'POST') {
    const parts = pathOnly.split('/');
    const amenityId = parts[parts.length - 2];
    const body = parseBody(options);
    const amn = state.amenities.find((a: any) => a.id === amenityId) || state.amenities[0];
    amn.is_active = Boolean(body.is_active);
    amn.updated_at = now;
    saveState(state);
    return amn as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/amenities\/staff\/[^/]+$/) && method === 'PATCH') {
    const amenityId = pathOnly.split('/').pop();
    const body = parseBody(options);
    const amn = state.amenities.find((a: any) => a.id === amenityId) || state.amenities[0];
    Object.assign(amn, body, { updated_at: now });
    saveState(state);
    return amn as unknown as T;
  }

  if (pathOnly === '/api/v1/amenities/bookings/me' || pathOnly === '/api/v1/amenities/staff/bookings') {
    return {
      items: state.amenityBookings,
      total: state.amenityBookings.length,
      page: 1,
      page_size: 20,
    } as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/amenities\/[^/]+\/slots$/)) {
    const parts = pathOnly.split('/');
    const amenityId = parts[parts.length - 2];
    const bookingDate = params.get('booking_date') || now.slice(0, 10);
    const amn = state.amenities.find((a: any) => a.id === amenityId) || state.amenities[0];
    return {
      amenity_id: amn.id,
      booking_date: bookingDate,
      slots: [
        {
          start_time: '07:00',
          end_time: '08:00',
          total_capacity: amn.capacity,
          booked_units: 0,
          remaining_capacity: amn.capacity,
          is_available: true,
          is_blocked: false,
        },
        {
          start_time: '08:00',
          end_time: '09:00',
          total_capacity: amn.capacity,
          booked_units: 1,
          remaining_capacity: Math.max(0, amn.capacity - 1),
          is_available: amn.capacity > 1,
          is_blocked: false,
        },
        {
          start_time: '18:00',
          end_time: '19:00',
          total_capacity: amn.capacity,
          booked_units: 0,
          remaining_capacity: amn.capacity,
          is_available: true,
          is_blocked: false,
        },
        {
          start_time: '19:00',
          end_time: '20:00',
          total_capacity: amn.capacity,
          booked_units: 0,
          remaining_capacity: amn.capacity,
          is_available: true,
          is_blocked: false,
        },
      ],
    } as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/amenities\/[^/]+\/bookings$/) && method === 'POST') {
    const parts = pathOnly.split('/');
    const amenityId = parts[parts.length - 2];
    const body = parseBody(options);
    const amn = state.amenities.find((a: any) => a.id === amenityId) || state.amenities[0];
    const booking = {
      id: 'bk-' + Date.now(),
      society_id: SOCIETY_ID,
      amenity_id: amn.id,
      amenity_name: amn.name,
      amenity_type: amn.amenity_type,
      flat_id: body.flat_id || activeFlatId,
      flat_number: profile.memberships?.[0]?.flat_number || '1203',
      tower_number: profile.memberships?.[0]?.tower_number || 'T07',
      user_id: profile.user.id,
      resident_name: profile.user.full_name,
      booking_date: body.booking_date || now.slice(0, 10),
      start_time: body.start_time || '18:00',
      end_time: body.end_time || '19:00',
      guests_count: body.guests_count || 1,
      status: 'CONFIRMED',
      fee_paise: amn.booking_fee_paise,
      payment_status: amn.booking_fee_paise > 0 ? 'PAID' : 'NOT_REQUIRED',
      notes: body.notes || null,
      created_at: now,
      updated_at: now,
    };
    state.amenityBookings.unshift(booking);
    saveState(state);
    return booking as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/amenities\/[^/]+$/)) {
    const amenityId = pathOnly.split('/').pop();
    return (state.amenities.find((a: any) => a.id === amenityId) || state.amenities[0]) as unknown as T;
  }

  // 6. Notifications & Official Notices
  if (pathOnly === '/api/v1/notifications/me') {
    return {
      items: state.notifications,
      total: state.notifications.length,
      page: 1,
      page_size: 20,
      unread_count: state.notifications.filter((n: any) => !n.is_read).length,
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/me/unread-count') {
    return {
      unread_count: state.notifications.filter((n: any) => !n.is_read).length,
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/me/preferences') {
    return {
      in_app_enabled: true,
      email_enabled: true,
      sms_enabled: true,
      whatsapp_enabled: false,
      quiet_hours_start: '22:00',
      quiet_hours_end: '07:00',
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/staff/overview') {
    return {
      total_notifications: state.notifications.length,
      total_deliveries: state.notifications.length * 3,
      sent_count: state.notifications.length * 3,
      failed_count: 0,
      pending_count: 0,
      recent_deliveries: [],
      page: 1,
      page_size: 20,
      total: 0,
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/resident/notices') {
    const published = state.notices.filter((n: any) => n.status === 'PUBLISHED');
    return {
      items: published,
      total: published.length,
      page: 1,
      page_size: 20,
      unread_count: published.filter((n: any) => !n.is_read).length,
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/resident/notices/unread-count') {
    const published = state.notices.filter((n: any) => n.status === 'PUBLISHED');
    return {
      unread_count: published.filter((n: any) => !n.is_read).length,
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/staff/notices/overview') {
    return {
      total_notices: state.notices.length,
      published_count: state.notices.filter((n: any) => n.status === 'PUBLISHED').length,
      draft_count: state.notices.filter((n: any) => n.status === 'DRAFT').length,
      scheduled_count: state.notices.filter((n: any) => n.status === 'SCHEDULED').length,
      archived_count: state.notices.filter((n: any) => n.status === 'ARCHIVED').length,
      pinned_count: state.notices.filter((n: any) => n.is_pinned).length,
      emergency_count: state.notices.filter((n: any) => n.is_emergency).length,
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/staff/notices' && method === 'GET') {
    return {
      items: state.notices,
      total: state.notices.length,
      page: 1,
      page_size: 20,
      unread_count: 0,
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/staff/notices' && method === 'POST') {
    const body = parseBody(options);
    const shouldPublish = Boolean(body.publish_immediately);
    const created = {
      id: 'notice-' + Date.now(),
      society_id: SOCIETY_ID,
      title: body.title || 'Township Notice',
      body: body.body || '',
      category: body.category || 'GENERAL',
      priority: body.priority || 'NORMAL',
      status: shouldPublish ? 'PUBLISHED' : 'DRAFT',
      target_type: body.target_type || 'SOCIETY',
      target_tower_id: body.target_tower_id || null,
      target_flat_id: body.target_flat_id || null,
      target_tower_ids: body.target_tower_ids || [],
      target_flat_ids: body.target_flat_ids || [],
      is_pinned: Boolean(body.is_pinned),
      is_emergency: Boolean(body.is_emergency),
      version: 1,
      published_at: shouldPublish ? now : null,
      expires_at: body.expires_at || null,
      scheduled_publish_at: body.scheduled_publish_at || null,
      created_by: profile.user.id,
      author_name: profile.user.full_name,
      is_read: false,
      read_at: null,
      read_count: 0,
      created_at: now,
      updated_at: now,
    };
    state.notices.unshift(created);
    if (shouldPublish) {
      state.notifications.unshift({
        id: 'notif-' + Date.now(),
        society_id: SOCIETY_ID,
        recipient_user_id: '44444444-4444-4444-4444-444444440001',
        title: `Official Notice: ${created.title}`,
        body: created.body.slice(0, 140),
        event_type: 'notice.published',
        priority: created.priority,
        aggregate_type: 'notice',
        aggregate_id: created.id,
        deep_link: '/resident/notices',
        is_read: false,
        read_at: null,
        created_at: now,
      });
    }
    saveState(state);
    return created as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/notifications\/staff\/notices\/[^/]+\/publish$/) && method === 'POST') {
    const parts = pathOnly.split('/');
    const noticeId = parts[parts.length - 2];
    const notice = state.notices.find((n: any) => n.id === noticeId) || state.notices[0];
    notice.status = 'PUBLISHED';
    notice.published_at = now;
    notice.updated_at = now;
    state.notifications.unshift({
      id: 'notif-' + Date.now(),
      society_id: SOCIETY_ID,
      recipient_user_id: '44444444-4444-4444-4444-444444440001',
      title: `Official Notice: ${notice.title}`,
      body: notice.body.slice(0, 140),
      event_type: 'notice.published',
      priority: notice.priority,
      aggregate_type: 'notice',
      aggregate_id: notice.id,
      deep_link: '/resident/notices',
      is_read: false,
      read_at: null,
      created_at: now,
    });
    saveState(state);
    return notice as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/notifications\/staff\/notices\/[^/]+\/archive$/) && method === 'POST') {
    const parts = pathOnly.split('/');
    const noticeId = parts[parts.length - 2];
    const notice = state.notices.find((n: any) => n.id === noticeId) || state.notices[0];
    notice.status = 'ARCHIVED';
    notice.updated_at = now;
    saveState(state);
    return notice as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/staff/towers') {
    return state.towers as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/staff/flats') {
    return Object.values(state.flats) as unknown as T;
  }

  if (pathOnly === '/api/v1/notifications/staff/targeting-options') {
    return {
      towers: state.towers,
      flats: Object.values(state.flats),
    } as unknown as T;
  }

  // 7. Complaints
  if (pathOnly === '/api/v1/complaints/me' && method === 'GET') {
    return state.complaints.filter((c: any) => c.flat_id === activeFlatId) as unknown as T;
  }

  if (pathOnly === '/api/v1/complaints' && method === 'POST') {
    const body = parseBody(options);
    const created = {
      id: 'cmp-' + Date.now(),
      society_id: SOCIETY_ID,
      flat_id: body.flat_id || activeFlatId,
      flat_number: profile.memberships?.[0]?.flat_number || '1203',
      tower_number: profile.memberships?.[0]?.tower_number || 'T07',
      complaint_number: `CMP-202611-000${state.complaints.length + 1}`,
      title: body.title || 'Maintenance Request',
      description: body.description || '',
      category: body.category || 'GENERAL',
      priority: body.priority || 'MEDIUM',
      status: 'SUBMITTED',
      created_by: profile.user.id,
      creator_name: profile.user.full_name,
      assigned_to: '44444444-4444-4444-4444-444444440004',
      assignee_name: 'Rajesh Shinde',
      safety_escalated: false,
      safety_escalation_reason: null,
      ai_status: 'COMPLETED',
      ai_suggested_category: body.category || 'GENERAL',
      ai_confidence: 0.91,
      is_sla_breached: false,
      first_response_sla_breached: false,
      first_response_deadline: now,
      resolution_deadline: now,
      first_response_at: null,
      resolved_at: null,
      closed_at: null,
      reopened_count: 0,
      rating: null,
      feedback: null,
      duplicate_of_id: null,
      duplicate_candidates: [],
      comments: [],
      attachments: [],
      activities: [],
      created_at: now,
      updated_at: now,
    };
    state.complaints.unshift(created);
    saveState(state);
    return created as unknown as T;
  }

  if (pathOnly === '/api/v1/complaints/helpdesk/dashboard') {
    return {
      total_complaints: state.complaints.length,
      open_complaints: state.complaints.filter((c: any) => c.status === 'SUBMITTED').length,
      in_progress_complaints: state.complaints.filter((c: any) => c.status === 'IN_PROGRESS').length,
      resolved_complaints: state.complaints.filter((c: any) => c.status === 'RESOLVED').length,
      closed_complaints: state.complaints.filter((c: any) => c.status === 'CLOSED').length,
      sla_breached_count: 0,
      safety_escalated_count: 0,
      unassigned_count: 0,
      by_category: { PLUMBING: state.complaints.length },
      by_priority: { MEDIUM: state.complaints.length },
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/complaints/helpdesk/safety-alerts') {
    return [] as unknown as T;
  }

  if (pathOnly === '/api/v1/complaints/helpdesk') {
    return state.complaints as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/complaints\/helpdesk\/[^/]+\/status$/) && method === 'PATCH') {
    const parts = pathOnly.split('/');
    const cmpId = parts[parts.length - 2];
    const body = parseBody(options);
    const cmp = state.complaints.find((c: any) => c.id === cmpId) || state.complaints[0];
    cmp.status = body.status || cmp.status;
    cmp.updated_at = now;
    saveState(state);
    return cmp as unknown as T;
  }

  // 8. Gate & Visitor Management
  if (pathOnly === '/api/v1/gate/session') {
    return {
      guard_user_id: profile.user.id,
      guard_name: profile.user.full_name,
      society_id: SOCIETY_ID,
      society_name: 'Marvel Greenfield Residences',
      gate_id: GATE_1_ID,
      gate_number: 1,
      gate_name: 'Gate 1 - North Main',
      assigned_from: '2026-01-01T00:00:00Z',
      assigned_until: null,
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/gate/overview') {
    return {
      gate_id: GATE_1_ID,
      gate_name: 'Gate 1 - North Main',
      pending_approvals_count: state.visitors.filter((v: any) => v.approval_status === 'PENDING').length,
      active_inside_count: state.visitors.filter((v: any) => v.entry_status === 'CHECKED_IN').length,
      today_total_entries: state.visitors.length,
      today_exits_count: state.visitors.filter((v: any) => v.entry_status === 'CHECKED_OUT').length,
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/gate/flats') {
    return Object.values(state.flats).map((f: any) => ({
      flat_id: f.id,
      flat_number: f.flat_number,
      tower_id: f.tower_id,
      tower_number: f.tower_number,
      tower_name: f.tower_name,
    })) as unknown as T;
  }

  if (pathOnly === '/api/v1/gate/visitors/register' && method === 'POST') {
    const body = parseBody(options);
    const flat = state.flats[body.destination_flat_id] || state.flats[FLAT_1203_ID];
    const created = {
      id: 'vis-' + Date.now(),
      society_id: SOCIETY_ID,
      gate_id: GATE_1_ID,
      gate_name: 'Gate 1 - North Main',
      destination_flat_id: flat.id,
      flat_number: flat.flat_number,
      tower_number: flat.tower_number,
      visitor_name: body.visitor_name || 'Walk-in Visitor',
      phone_number: body.phone_number || '+919800011111',
      masked_phone: '+91-XXXXXX1111',
      vehicle_number: body.vehicle_number || null,
      purpose: body.purpose || 'GUEST',
      approval_status: 'PENDING',
      entry_status: 'EXPECTED',
      entry_time: null,
      exit_time: null,
      created_at: now,
      updated_at: now,
    };
    state.visitors.unshift(created);
    saveState(state);
    return created as unknown as T;
  }

  if (
    pathOnly === '/api/v1/gate/visitors' ||
    pathOnly === '/api/v1/gate/visitors/active' ||
    pathOnly === '/api/v1/gate/visitors/history'
  ) {
    return state.visitors as unknown as T;
  }

  if (pathOnly === '/api/v1/gate/privacy-notice') {
    return {
      version: 'v1.0-2026-pune',
      language: params.get('lang') || 'en',
      title: 'DPDP Act 2023 Visitor Data Privacy Notice',
      content:
        'Visitor photographs and phone numbers are collected solely for residential campus security and automatically purged after 30 days.',
    } as unknown as T;
  }

  if (
    pathOnly === '/api/v1/resident/visitors/pending' ||
    pathOnly === '/api/v1/resident/visitors/today' ||
    pathOnly === '/api/v1/resident/visitors/history'
  ) {
    return state.visitors.filter((v: any) => v.destination_flat_id === activeFlatId) as unknown as T;
  }

  if (pathOnly.match(/^\/api\/v1\/resident\/visitors\/[^/]+\/action$/) && method === 'POST') {
    const parts = pathOnly.split('/');
    const visitorId = parts[parts.length - 2];
    const body = parseBody(options);
    const vis = state.visitors.find((v: any) => v.id === visitorId) || state.visitors[0];
    vis.approval_status = body.action === 'APPROVE' ? 'APPROVED' : 'REJECTED';
    vis.updated_at = now;
    saveState(state);
    return {
      visitor_id: vis.id,
      approval_status: vis.approval_status,
      approved_at: now,
      action_by_user_id: profile.user.id,
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/resident/passes' && method === 'GET') {
    return state.guestPasses.filter((p: any) => p.destination_flat_id === activeFlatId) as unknown as T;
  }

  if (pathOnly === '/api/v1/resident/passes' && method === 'POST') {
    const body = parseBody(options);
    const code = `GP-${Math.random().toString(36).slice(2, 6).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}-DEMO`;
    const created = {
      pass_id: 'gp-' + Date.now(),
      id: 'gp-' + Date.now(),
      society_id: SOCIETY_ID,
      destination_flat_id: body.destination_flat_id || activeFlatId,
      flat_number: profile.memberships?.[0]?.flat_number || '1203',
      tower_number: profile.memberships?.[0]?.tower_number || 'T07',
      guest_name: body.guest_name || 'Invited Guest',
      guest_phone: body.guest_phone || '+919800012345',
      purpose: body.purpose || 'Personal Visit',
      pass_type: body.pass_type || 'SINGLE_USE',
      pass_code_prefix: 'GP-',
      pass_code: code,
      status: 'ACTIVE',
      max_uses: body.max_uses || 1,
      used_count: 0,
      valid_from: body.valid_from || now,
      valid_until: body.valid_until || now,
      created_at: now,
    };
    state.guestPasses.unshift(created);
    saveState(state);
    return created as unknown as T;
  }

  // 9. Registry
  if (pathOnly === '/api/v1/registry/residents') {
    return state.residents as unknown as T;
  }

  // 10. Reconciliation
  if (pathOnly === '/api/v1/reconciliation/summary') {
    return {
      total_transactions: 3,
      auto_matched_count: 2,
      manual_review_count: 1,
      approved_count: 2,
      rejected_count: 0,
      unidentified_count: 0,
      total_credit_paise: 1247500,
      total_reconciled_paise: 1247500,
      unreconciled_paise: 0,
    } as unknown as T;
  }

  if (
    pathOnly === '/api/v1/reconciliation/statements' ||
    pathOnly === '/api/v1/reconciliation/transactions' ||
    pathOnly === '/api/v1/reconciliation/queue'
  ) {
    return [] as unknown as T;
  }

  if (pathOnly === '/api/v1/reconciliation/upi-mappings') {
    return state.upiMappings as unknown as T;
  }

  // 11. Committee Governance Overview
  if (pathOnly === '/api/v1/committee/overview') {
    const totalBilled = state.invoices.reduce((s: number, i: any) => s + i.total_paise, 0);
    const totalCollected = state.invoices.reduce((s: number, i: any) => s + i.paid_paise, 0);
    const totalOutstanding = totalBilled - totalCollected;
    return {
      society_id: SOCIETY_ID,
      society_name: 'Marvel Greenfield Residences',
      as_of_date: now,
      financials: {
        total_billed_paise: totalBilled,
        total_collected_paise: totalCollected,
        total_outstanding_paise: totalOutstanding,
        total_overdue_paise: 637000,
        collection_percentage: Number(((totalCollected / totalBilled) * 100).toFixed(1)),
        ageing: {
          bucket_0_30_paise: 566000,
          bucket_31_60_paise: 637000,
          bucket_61_90_paise: 0,
          bucket_90_plus_paise: 0,
        },
      },
      complaints: {
        total_complaints: state.complaints.length,
        open_complaints: state.complaints.filter((c: any) => c.status === 'SUBMITTED').length,
        in_progress_complaints: state.complaints.filter((c: any) => c.status === 'IN_PROGRESS').length,
        resolved_complaints: state.complaints.filter((c: any) => c.status === 'RESOLVED').length,
        closed_complaints: state.complaints.filter((c: any) => c.status === 'CLOSED').length,
        safety_escalated_count: 0,
        sla_breached_count: 0,
        first_response_sla_breached_count: 0,
        reopened_count: 0,
        avg_resolution_hours: 4.2,
        median_resolution_hours: 3.8,
        avg_first_response_hours: 0.5,
        median_first_response_hours: 0.4,
      },
      towers: [
        {
          tower_id: TOWER_T07_ID,
          tower_number: 'T07',
          tower_name: 'Tower 7',
          total_flats: 84,
          total_billed_paise: 747500,
          total_collected_paise: 0,
          total_outstanding_paise: 747500,
          open_complaints: 1,
        },
        {
          tower_id: TOWER_T12_ID,
          tower_number: 'T12',
          tower_name: 'Tower 12',
          total_flats: 84,
          total_billed_paise: 637000,
          total_collected_paise: 0,
          total_outstanding_paise: 637000,
          open_complaints: 0,
        },
        {
          tower_id: TOWER_T21_ID,
          tower_number: 'T21',
          tower_name: 'Tower 21',
          total_flats: 64,
          total_billed_paise: 1066000,
          total_collected_paise: 500000,
          total_outstanding_paise: 566000,
          open_complaints: 0,
        },
      ],
    } as unknown as T;
  }

  if (pathOnly === '/api/v1/committee/reports/monthly') {
    return [
      {
        billing_period: '2026-11',
        total_invoices: 3,
        total_billed_paise: 2450500,
        total_collected_paise: 500000,
        total_outstanding_paise: 1950500,
        collection_percentage: 20.4,
      },
    ] as unknown as T;
  }

  return {} as T;
}


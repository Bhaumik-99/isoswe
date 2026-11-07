export interface TranslationDictionary {
  common: {
    appName: string;
    loading: string;
    refresh: string;
    close: string;
    cancel: string;
    submit: string;
    search: string;
    clear: string;
    online: string;
    offline: string;
    languageLabel: string;
    backToStaff: string;
    logout: string;
    optional: string;
    required: string;
    viewPhoto: string;
    photoExpired: string;
    noData: string;
  };
  privacyNotice: {
    version: string;
    badgeLabel: string;
    buttonLabel: string;
    modalTitle: string;
    collectionTitle: string;
    collectionBody: string;
    purposeTitle: string;
    purposeBody: string;
    accessTitle: string;
    accessBody: string;
    retentionTitle: string;
    retentionBody: string;
    grievanceTitle: string;
    grievanceBody: string;
    acknowledgmentLabel: string;
  };
  gate: {
    tabletTitle: string;
    tabletSubtitle: string;
    assignedGateLabel: string;
    switchGateLabel: string;
    operatorLabel: string;
    kpiTodayVisitors: string;
    kpiCurrentlyInside: string;
    kpiPendingApprovals: string;
    kpiCheckedOutToday: string;
    kpiOfflineQueue: string;
    tabs: {
      register: string;
      passVerify: string;
      liveMonitor: string;
      campusExit: string;
      history: string;
    };
    registration: {
      sectionTitle: string;
      sectionSubtitle: string;
      visitorNameLabel: string;
      visitorNamePlaceholder: string;
      phoneLabel: string;
      phonePlaceholder: string;
      vehicleLabel: string;
      vehiclePlaceholder: string;
      destinationFlatLabel: string;
      destinationFlatPlaceholder: string;
      purposeLabel: string;
      purposes: {
        PERSONAL_GUEST: string;
        DELIVERY: string;
        CAB_TAXI: string;
        SERVICE_REPAIR: string;
        DOMESTIC_HELP: string;
        COURIER: string;
        OTHER: string;
      };
      photoSectionLabel: string;
      captureCameraBtn: string;
      uploadPhotoBtn: string;
      retakePhotoBtn: string;
      photoCapturedReady: string;
      photoOptionalOfflineNote: string;
      submitOnlineBtn: string;
      submitOfflineBtn: string;
      offlineBannerTitle: string;
      offlineBannerBody: string;
      registeredSuccessOnline: string;
      registeredSuccessOffline: string;
    };
    passVerification: {
      sectionTitle: string;
      sectionSubtitle: string;
      passCodeLabel: string;
      passCodePlaceholder: string;
      verifyBtn: string;
      offlineDisabledTitle: string;
      offlineDisabledBody: string;
      verifiedSuccessTitle: string;
      verifiedSuccessBody: string;
      usesRemainingLabel: string;
    };
    liveMonitor: {
      sectionTitle: string;
      sectionSubtitle: string;
      filterAll: string;
      filterPending: string;
      filterApproved: string;
      filterRejected: string;
      checkInBtn: string;
      awaitingResidentNotice: string;
      rejectedByResidentNotice: string;
      checkedInSuccess: string;
    };
    campusExit: {
      sectionTitle: string;
      sectionSubtitle: string;
      searchPlaceholder: string;
      checkOutBtn: string;
      noInsideVisitors: string;
      checkedOutSuccess: string;
    };
    history: {
      sectionTitle: string;
      sectionSubtitle: string;
      searchPlaceholder: string;
      colVisitor: string;
      colPhone: string;
      colFlat: string;
      colPurpose: string;
      colApproval: string;
      colEntryStatus: string;
      colTimestamps: string;
      colActions: string;
    };
    offlineDrawer: {
      drawerTitle: string;
      drawerSubtitle: string;
      syncNowBtn: string;
      retryFailedBtn: string;
      clearSyncedBtn: string;
      emptyQueueMessage: string;
      statusQueued: string;
      statusSyncing: string;
      statusSynced: string;
      statusConflict: string;
      statusFailed: string;
      pendingApprovalRuleNote: string;
    };
  };
  resident: {
    pageTitle: string;
    pageSubtitle: string;
    homeCardTitle: string;
    homeCardSubtitle: string;
    homePendingBadge: string;
    homeNoPendingBadge: string;
    homeManageCta: string;
    tabs: {
      pending: string;
      today: string;
      passes: string;
      history: string;
    };
    pendingInbox: {
      title: string;
      subtitle: string;
      emptyMessage: string;
      approveBtn: string;
      rejectBtn: string;
      rejectionReasonPlaceholder: string;
      confirmRejectBtn: string;
      approvedToast: string;
      rejectedToast: string;
    };
    todayFeed: {
      title: string;
      subtitle: string;
      emptyMessage: string;
    };
    guestPasses: {
      createTitle: string;
      createSubtitle: string;
      visitorNameLabel: string;
      visitorPhoneLabel: string;
      purposeLabel: string;
      passTypeLabel: string;
      singleUseOption: string;
      multiUseOption: string;
      maxUsesLabel: string;
      validHoursLabel: string;
      generateBtn: string;
      generatedCodeBannerTitle: string;
      generatedCodeBannerSubtitle: string;
      copyCodeBtn: string;
      copiedLabel: string;
      activePassesTitle: string;
      revokeBtn: string;
      revokedSuccess: string;
      emptyPassesMessage: string;
    };
    history: {
      title: string;
      subtitle: string;
      emptyMessage: string;
    };
  };
  statuses: {
    approval: {
      PENDING: string;
      APPROVED: string;
      REJECTED: string;
      AUTO_APPROVED: string;
    };
    entry: {
      EXPECTED: string;
      CHECKED_IN: string;
      CHECKED_OUT: string;
    };
    pass: {
      ACTIVE: string;
      REDEEMED: string;
      EXPIRED: string;
      REVOKED: string;
    };
  };
  errors: {
    nameRequired: string;
    phoneInvalid: string;
    flatRequired: string;
    purposeRequired: string;
    passCodeRequired: string;
    cameraUnavailable: string;
    photoExpired410: string;
    rateLimited429: string;
    conflict409: string;
    genericError: string;
  };
  notices: {
    title: string;
    subtitle: string;
    overviewTitle: string;
    emergencyAlerts: string;
    pinnedNotices: string;
    latestAnnouncements: string;
    filters: {
      all: string;
      unread: string;
      general: string;
      circular: string;
      maintenance: string;
      water: string;
      electricity: string;
      security: string;
      event: string;
      emergency: string;
    };
    statuses: {
      draft: string;
      scheduled: string;
      published: string;
      archived: string;
    };
    priorities: {
      low: string;
      normal: string;
      high: string;
      urgent: string;
    };
    actions: {
      compose: string;
      edit: string;
      publish: string;
      schedule: string;
      archive: string;
      markRead: string;
      markAllRead: string;
      refresh: string;
      viewDetails: string;
      filter: string;
    };
    composer: {
      modalTitle: string;
      editModalTitle: string;
      titleLabel: string;
      titlePlaceholder: string;
      bodyLabel: string;
      bodyPlaceholder: string;
      categoryLabel: string;
      priorityLabel: string;
      targetAudienceLabel: string;
      selectTowers: string;
      selectFlats: string;
      publishNowLabel: string;
      scheduleLabel: string;
      scheduledTimeLabel: string;
      expiryDateLabel: string;
      pinnedLabel: string;
      emergencyConfirmLabel: string;
      saveDraftBtn: string;
      publishBtn: string;
      scheduleBtn: string;
    };
    kpi: {
      total: string;
      published: string;
      scheduled: string;
      drafts: string;
      archived: string;
      emergencies: string;
    };
    emptyState: string;
    emptyDesc: string;
    readReceipt: string;
    unread: string;
    read: string;
  };
}

export const enDictionary: TranslationDictionary = {
  common: {
    appName: 'Marvel Greenfield Gate & Visitor Operations',
    loading: 'Loading...',
    refresh: 'Refresh',
    close: 'Close',
    cancel: 'Cancel',
    submit: 'Submit',
    search: 'Search',
    clear: 'Clear',
    online: 'ONLINE',
    offline: 'OFFLINE MODE',
    languageLabel: 'Language',
    backToStaff: 'Staff Portal',
    logout: 'Sign Out',
    optional: 'Optional',
    required: 'Required',
    viewPhoto: 'View Photo',
    photoExpired: 'Photo Expired (90-Day Policy)',
    noData: 'No records found',
  },
  privacyNotice: {
    version: 'v1.0-2026-pune',
    badgeLabel: 'Privacy Notice v1.0-2026-pune',
    buttonLabel: 'Gate Privacy Notice',
    modalTitle: 'Visitor Data Protection & Privacy Notice (DPDP Act Compliant)',
    collectionTitle: '1. Information Collected at Gate',
    collectionBody:
      'We collect the visitor full name, mobile phone number, optional vehicle registration number, destination tower/flat, visit purpose, entry/exit timestamps, and a live facial photograph at the township entrance gate.',
    purposeTitle: '2. Purpose of Collection',
    purposeBody:
      'This data is collected strictly for residential township security, real-time resident verification and approval, and emergency campus safety audit logs at Marvel Greenfield Township, Pune.',
    accessTitle: '3. Authorized Access Boundaries',
    accessBody:
      'Your visitor record and photograph are accessible strictly to authorized residents of your destination flat and on-duty assigned gate security personnel. Cross-flat or public access is prohibited.',
    retentionTitle: '4. Mandatory 90-Day Photograph Retention',
    retentionBody:
      'Visitor photographs are stored in private encrypted storage and are automatically and permanently purged 90 days after capture.',
    grievanceTitle: '5. Data Protection & Grievance Contact',
    grievanceBody:
      'Data Protection Officer, Marvel Greenfield Co-operative Housing Society Ltd., Pune — Email: privacy@greenfield-pune.org | Helpdesk Ext: 100.',
    acknowledgmentLabel:
      'Privacy Notice (v1.0-2026-pune) displayed and explained to visitor prior to registration.',
  },
  gate: {
    tabletTitle: 'Township Gate Security Console',
    tabletSubtitle: 'High-Contrast Tablet Interface • 4 Entrance Gates • Offline-Resilient',
    assignedGateLabel: 'Active Gate',
    switchGateLabel: 'Switch Gate',
    operatorLabel: 'Guard on Duty',
    kpiTodayVisitors: "Today's Visitors",
    kpiCurrentlyInside: 'Currently Inside',
    kpiPendingApprovals: 'Pending Approval',
    kpiCheckedOutToday: 'Checked Out Today',
    kpiOfflineQueue: 'Offline Queue',
    tabs: {
      register: 'Register Visitor',
      passVerify: 'Verify Guest Pass',
      liveMonitor: 'Approval & Entry',
      campusExit: 'Record Exit',
      history: 'Visitor Log',
    },
    registration: {
      sectionTitle: 'New Visitor Registration',
      sectionSubtitle: 'Capture visitor details, photograph, and request resident approval',
      visitorNameLabel: 'Visitor Full Name',
      visitorNamePlaceholder: 'Enter visitor full name (e.g., Ramesh Pawar)',
      phoneLabel: 'Mobile Number (10-digit / +91)',
      phonePlaceholder: 'e.g., 9823011223',
      vehicleLabel: 'Vehicle Number (Optional)',
      vehiclePlaceholder: 'e.g., MH-12-AB-1234',
      destinationFlatLabel: 'Destination Tower & Flat',
      destinationFlatPlaceholder: 'Select destination flat...',
      purposeLabel: 'Purpose of Visit',
      purposes: {
        PERSONAL_GUEST: 'Personal Guest / Family',
        DELIVERY: 'Parcel / Food Delivery',
        CAB_TAXI: 'Cab / Auto Pickup-Drop',
        SERVICE_REPAIR: 'Appliance / Home Repair',
        DOMESTIC_HELP: 'Domestic Help / Cook',
        COURIER: 'Official Courier / Post',
        OTHER: 'Other Authorized Visit',
      },
      photoSectionLabel: 'Visitor Photograph (90-Day Retention)',
      captureCameraBtn: 'Open Tablet Camera',
      uploadPhotoBtn: 'Upload Photo File',
      retakePhotoBtn: 'Clear / Retake Photo',
      photoCapturedReady: 'Visitor photograph attached and verified',
      photoOptionalOfflineNote: 'Photos captured offline are stored in local IndexedDB until synced.',
      submitOnlineBtn: 'Register & Request Resident Approval',
      submitOfflineBtn: 'Queue Visitor in Offline Storage (PENDING)',
      offlineBannerTitle: 'Tablet is Offline — Local Queue Active',
      offlineBannerBody:
        'Registrations are saved locally in IndexedDB with a tamper-evident SHA-256 signature and will sync as PENDING when connectivity returns.',
      registeredSuccessOnline: 'Visitor registered and approval request sent to flat resident.',
      registeredSuccessOffline:
        'Visitor saved to Offline Queue with PENDING status. Will sync automatically upon reconnection.',
    },
    passVerification: {
      sectionTitle: 'Pre-Approved Guest Pass Verification',
      sectionSubtitle: 'Redeem single-use or multi-use resident guest code (GP-XXXX-XXXX-XXXX)',
      passCodeLabel: 'Guest Pass Code',
      passCodePlaceholder: 'GP-XXXX-XXXX-XXXX',
      verifyBtn: 'Verify & Redeem Guest Pass',
      offlineDisabledTitle: 'Guest Pass Verification Unavailable Offline (Fail-Closed)',
      offlineDisabledBody:
        'To prevent pass replay or revoked pass misuse, guest pass codes require live server verification. While offline, please register the visitor manually using the Register Visitor tab so it queues as PENDING.',
      verifiedSuccessTitle: 'Guest Pass Verified & Auto-Approved',
      verifiedSuccessBody: 'Pass redeemed transactionally. You may now record entry from Approval & Entry.',
      usesRemainingLabel: 'Redemptions Used',
    },
    liveMonitor: {
      sectionTitle: 'Live Resident Approval & Gate Entry Queue',
      sectionSubtitle: 'Guard can record physical entry only after status is APPROVED or AUTO_APPROVED',
      filterAll: 'All Active',
      filterPending: 'Pending',
      filterApproved: 'Approved',
      filterRejected: 'Rejected',
      checkInBtn: 'Record Entry (Check In)',
      awaitingResidentNotice: 'Waiting for resident in-app approval...',
      rejectedByResidentNotice: 'Entry denied by resident',
      checkedInSuccess: 'Visitor physical entry recorded at gate.',
    },
    campusExit: {
      sectionTitle: 'Currently Inside Campus — Record Exit',
      sectionSubtitle: 'Mark departure timestamp and exit gate for checked-in visitors',
      searchPlaceholder: 'Search by visitor name, vehicle, or phone...',
      checkOutBtn: 'Record Exit (Check Out)',
      noInsideVisitors: 'No visitors are currently checked in inside the campus.',
      checkedOutSuccess: 'Visitor departure recorded at gate.',
    },
    history: {
      sectionTitle: 'Scoped Gate Visitor Register',
      sectionSubtitle: 'Audited visitor log with 90-day privacy-protected photo access',
      searchPlaceholder: 'Search visitor name or phone...',
      colVisitor: 'Visitor',
      colPhone: 'Phone / Vehicle',
      colFlat: 'Destination Flat',
      colPurpose: 'Purpose',
      colApproval: 'Approval State',
      colEntryStatus: 'Entry State',
      colTimestamps: 'Timestamps',
      colActions: 'Photo / Audit',
    },
    offlineDrawer: {
      drawerTitle: 'Offline Event Queue & Replay-Protected Sync',
      drawerSubtitle: 'IndexedDB persistent queue with per-event ACK and tamper detection',
      syncNowBtn: 'Sync Queued Events Now',
      retryFailedBtn: 'Retry Failed Events',
      clearSyncedBtn: 'Clear Acknowledged',
      emptyQueueMessage: 'No offline visitor events queued on this tablet.',
      statusQueued: 'QUEUED OFFLINE',
      statusSyncing: 'SYNCING...',
      statusSynced: 'SYNCED (ACK)',
      statusConflict: 'CONFLICT (409 TAMPER)',
      statusFailed: 'SYNC FAILED',
      pendingApprovalRuleNote:
        'Security Invariant: Offline events never grant automatic entry; synced records enter PENDING state.',
    },
  },
  resident: {
    pageTitle: 'Gate Visitors & Pre-Approved Guest Passes',
    pageSubtitle: 'Approve visitors at the gate, view today’s arrivals, and issue guest codes for your flat',
    homeCardTitle: 'Gate Visitors & Pre-Approved Passes',
    homeCardSubtitle: 'Real-time gate approval requests and digital guest pass codes',
    homePendingBadge: 'Pending at Gate',
    homeNoPendingBadge: 'Gate Clear',
    homeManageCta: 'Manage Visitors & Guest Passes',
    tabs: {
      pending: 'Pending Approvals',
      today: "Today's Visitors",
      passes: 'Guest Passes',
      history: 'Visitor History',
    },
    pendingInbox: {
      title: 'Visitors Waiting for Your Decision',
      subtitle: 'Approve or reject entry requests submitted by gate guards for your flat',
      emptyMessage: 'No visitors are currently waiting for approval for your flat.',
      approveBtn: 'Approve Entry',
      rejectBtn: 'Reject',
      rejectionReasonPlaceholder: 'Reason for rejection (e.g., Unexpected delivery)',
      confirmRejectBtn: 'Confirm Rejection',
      approvedToast: 'Visitor approved! Gate guard has been notified.',
      rejectedToast: 'Visitor entry rejected.',
    },
    todayFeed: {
      title: "Today's & Expected Visitors",
      subtitle: 'Real-time status of visitors who arrived or are expected at your flat today',
      emptyMessage: 'No visitor arrivals recorded for your flat today.',
    },
    guestPasses: {
      createTitle: 'Create Pre-Approved Guest Pass',
      createSubtitle: 'Generate a secure single-use or multi-use pass code (GP-XXXX) for expected guests',
      visitorNameLabel: 'Guest Full Name',
      visitorPhoneLabel: 'Guest Mobile Number (Optional)',
      purposeLabel: 'Visit Purpose',
      passTypeLabel: 'Pass Type',
      singleUseOption: 'Single-Use Pass (1 Entry)',
      multiUseOption: 'Multi-Use Pass (2 to 10 Entries)',
      maxUsesLabel: 'Maximum Allowed Entries (2–10)',
      validHoursLabel: 'Validity Duration (Hours)',
      generateBtn: 'Generate Secure Guest Pass',
      generatedCodeBannerTitle: 'Save Your One-Time Guest Pass Code Now',
      generatedCodeBannerSubtitle:
        'For security, only a salted cryptographic hash is stored on the server. Share this code with your guest:',
      copyCodeBtn: 'Copy Pass Code',
      copiedLabel: 'Copied!',
      activePassesTitle: 'Issued Guest Passes for Your Flat',
      revokeBtn: 'Revoke Pass',
      revokedSuccess: 'Guest pass revoked immediately.',
      emptyPassesMessage: 'No guest passes created for this flat yet.',
    },
    history: {
      title: 'Flat Visitor History',
      subtitle: 'Complete log of past visitors, entry/exit timestamps, and approvals for your unit',
      emptyMessage: 'No historical visitor records found for this flat.',
    },
  },
  statuses: {
    approval: {
      PENDING: 'Pending Approval',
      APPROVED: 'Approved',
      REJECTED: 'Rejected',
      AUTO_APPROVED: 'Auto-Approved (Pass)',
    },
    entry: {
      EXPECTED: 'At Gate / Expected',
      CHECKED_IN: 'Inside Campus',
      CHECKED_OUT: 'Checked Out',
    },
    pass: {
      ACTIVE: 'Active',
      REDEEMED: 'Fully Redeemed',
      EXPIRED: 'Expired',
      REVOKED: 'Revoked',
    },
  },
  errors: {
    nameRequired: 'Please enter the visitor full name.',
    phoneInvalid: 'Please enter a valid 10-digit Indian mobile number.',
    flatRequired: 'Please select a destination tower and flat.',
    purposeRequired: 'Please select or enter the purpose of visit.',
    passCodeRequired: 'Please enter a valid GP-XXXX pass code.',
    cameraUnavailable: 'Camera stream unavailable on this device. Please use File Upload fallback.',
    photoExpired410: 'This visitor photograph has expired under the mandatory 90-day retention policy.',
    rateLimited429: 'Too many invalid guest pass attempts at this gate. Locked for 10 minutes.',
    conflict409: 'Replay conflict detected (409): Offline event payload was modified after capture.',
    genericError: 'Unable to complete request. Please check your connection and try again.',
  },
  notices: {
    title: 'Official Township Notices & Communications',
    subtitle: 'Official federation circulars, maintenance advisories, and emergency announcements',
    overviewTitle: 'Notice Management Overview',
    emergencyAlerts: 'Emergency Announcements',
    pinnedNotices: 'Pinned Notices',
    latestAnnouncements: 'Latest Notices',
    filters: {
      all: 'All Notices',
      unread: 'Unread Only',
      general: 'General',
      circular: 'Circular',
      maintenance: 'Maintenance',
      water: 'Water Supply',
      electricity: 'Electricity',
      security: 'Security',
      event: 'Events',
      emergency: 'Emergency',
    },
    statuses: {
      draft: 'Draft',
      scheduled: 'Scheduled',
      published: 'Published',
      archived: 'Archived',
    },
    priorities: {
      low: 'Low',
      normal: 'Normal',
      high: 'High',
      urgent: 'Urgent',
    },
    actions: {
      compose: 'Compose Notice',
      edit: 'Edit Notice',
      publish: 'Publish',
      schedule: 'Schedule',
      archive: 'Archive',
      markRead: 'Mark as Read',
      markAllRead: 'Mark All Read',
      refresh: 'Refresh',
      viewDetails: 'View Details',
      filter: 'Filter',
    },
    composer: {
      modalTitle: 'Compose Official Notice',
      editModalTitle: 'Edit Official Notice',
      titleLabel: 'Notice Title',
      titlePlaceholder: 'e.g., Scheduled Water Tank Cleaning - Tower T01 to T07',
      bodyLabel: 'Notice Content & Guidelines',
      bodyPlaceholder: 'Detail the schedule, impact, precautions, and contacts...',
      categoryLabel: 'Category',
      priorityLabel: 'Priority',
      targetAudienceLabel: 'Target Audience Scope',
      selectTowers: 'Select Towers',
      selectFlats: 'Select Specific Flats',
      publishNowLabel: 'Publish Immediately',
      scheduleLabel: 'Schedule for Later',
      scheduledTimeLabel: 'Scheduled Publication Date & Time',
      expiryDateLabel: 'Notice Expiry Date (Optional)',
      pinnedLabel: 'Pin this notice to top of feed',
      emergencyConfirmLabel: 'Broadcast as High-Priority Emergency Notice (bypasses resident opt-outs)',
      saveDraftBtn: 'Save Draft',
      publishBtn: 'Publish Notice',
      scheduleBtn: 'Schedule Publication',
    },
    kpi: {
      total: 'Total Notices',
      published: 'Published',
      scheduled: 'Scheduled',
      drafts: 'Drafts',
      archived: 'Archived',
      emergencies: 'Emergency Alerts',
    },
    emptyState: 'No notices available',
    emptyDesc: 'There are currently no official notices published for your unit or society.',
    readReceipt: 'Read receipt recorded',
    unread: 'Unread',
    read: 'Read',
  },
};


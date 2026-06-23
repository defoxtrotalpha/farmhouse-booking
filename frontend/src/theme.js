// ---------------------------------------------------------------------------
// Estate Ledger — design system tokens
//
// A private farmhouse/estate booking tool for trusted agents in Asia/Karachi.
// Identity: a calm "estate concierge ledger" — pine + brass on warm linen,
// a characterful Fraunces display, and booking numbers set in mono like a
// real ledger. Deliberately avoids generic SaaS / AI-default looks.
// ---------------------------------------------------------------------------

export const brand = {
  pine: "#1F3D33", // primary — hedge green, calm authority
  pineDeep: "#16302792",
  pineSoft: "#2E5246",
  brass: "#C0892D", // signature accent — lantern / estate hardware
  brassSoft: "#E8D6A8",
  linen: "#F4F0E7", // app background — warm paper
  paper: "#FFFFFF",
  ink: "#22281F", // near-black, green-tinted
  muted: "#6F7568",
  hairline: "#E6E0D2",
};

// Booking lifecycle status palette, tuned into the estate palette.
export const STATUS = {
  hold: { color: "#9A6B16", bg: "#F6ECD7", label: "Hold", dot: "#C0892D" },
  pending: { color: "#3C5876", bg: "#E4ECF4", label: "Pending", dot: "#4C6B8A" },
  booked: { color: "#235B3E", bg: "#DDEBE1", label: "Booked", dot: "#2E6F4E" },
  rejected: { color: "#8C3A30", bg: "#F3E0DC", label: "Rejected", dot: "#A8453A" },
  canceled: { color: "#6F6A5D", bg: "#ECE9E1", label: "Canceled", dot: "#8A8475" },
  expired: { color: "#7E796E", bg: "#ECEAE3", label: "Expired", dot: "#A9A395" },
};

export function statusOf(s) {
  return STATUS[s] ?? { color: brand.muted, bg: "#EEEBE3", label: s, dot: brand.muted };
}

const FONT_BODY =
  "'Hanken Grotesk', system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
const FONT_DISPLAY = "'Fraunces', Georgia, 'Times New Roman', serif";

// Ant Design theme — maps the Estate Ledger tokens onto antd v5.
export const antdTheme = {
  token: {
    colorPrimary: brand.pine,
    colorInfo: brand.pine,
    colorSuccess: "#2E6F4E",
    colorWarning: "#C0892D",
    colorError: "#A8453A",
    colorTextBase: brand.ink,
    colorBgBase: brand.paper,
    colorBgLayout: brand.linen,
    colorBorder: brand.hairline,
    colorBorderSecondary: brand.hairline,
    borderRadius: 12,
    borderRadiusLG: 16,
    borderRadiusSM: 8,
    fontFamily: FONT_BODY,
    fontSize: 15,
    controlHeight: 42,
    controlHeightLG: 48,
    lineHeight: 1.55,
    wireframe: false,
    boxShadow: "0 1px 2px rgba(34,40,31,0.05), 0 8px 24px -12px rgba(34,40,31,0.16)",
    boxShadowSecondary: "0 6px 20px -10px rgba(34,40,31,0.22)",
  },
  components: {
    Button: {
      fontWeight: 600,
      primaryShadow: "none",
      defaultShadow: "none",
      controlHeight: 42,
      controlHeightLG: 48,
    },
    Card: {
      borderRadiusLG: 18,
      paddingLG: 22,
      colorBorderSecondary: brand.hairline,
    },
    Segmented: {
      trackBg: "#EAE5D8",
      itemSelectedBg: brand.paper,
      itemSelectedColor: brand.pine,
      borderRadius: 12,
    },
    Tabs: {
      inkBarColor: brand.brass,
      itemSelectedColor: brand.pine,
      itemActiveColor: brand.pine,
      titleFontSize: 15,
    },
    Modal: { borderRadiusLG: 20, paddingContentHorizontalLG: 26 },
    Drawer: {},
    Input: { controlHeight: 44, activeShadow: "0 0 0 3px rgba(31,61,51,0.08)" },
    Select: { controlHeight: 44 },
    DatePicker: { controlHeight: 44 },
    Table: {
      headerBg: "#F2EEE4",
      headerColor: brand.muted,
      borderColor: brand.hairline,
      rowHoverBg: "#FBF9F4",
    },
    Tag: { borderRadiusSM: 999 },
    Menu: {
      itemSelectedBg: "#EAF0EC",
      itemSelectedColor: brand.pine,
      itemBorderRadius: 10,
      itemHeight: 44,
    },
    Statistic: { titleFontSize: 13 },
  },
};

export const FONTS = { body: FONT_BODY, display: FONT_DISPLAY };

// Booking number, ledger-style: #0042
export function bookingNo(id) {
  return "#" + String(id).padStart(4, "0");
}

// Format a UTC ISO timestamp in Asia/Karachi.
export function fmtDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", {
    timeZone: "Asia/Karachi",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", {
    timeZone: "Asia/Karachi",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-GB", {
    timeZone: "Asia/Karachi",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

// "3 hr 30 min" style duration between two ISO timestamps.
export function fmtDuration(startIso, endIso) {
  const mins = Math.max(0, Math.round((new Date(endIso) - new Date(startIso)) / 60000));
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h && m) return `${h} hr ${m} min`;
  if (h) return `${h} hr`;
  return `${m} min`;
}

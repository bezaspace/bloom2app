import { getToken } from "./auth";
import { HTTP_BASE } from "./config";

/** Supported MIME types for health document uploads. */
export const SUPPORTED_DOC_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
];

/** A structured summary extracted from an uploaded health document. */
export interface DocumentSummary {
  conditions: string[];
  medications: string[];
  allergies: string[];
  recent_labs: string[];
  lifestyle_notes: string;
  red_flags: string[];
  free_text_summary: string;
}

/** A phase in the 90-day wellness plan. */
export interface PlanPhase {
  name: string;
  focus: string;
  actions: string[];
}

/** The 90-day wellness plan stored after onboarding. */
export interface WellnessPlan {
  summary: string;
  phases: PlanPhase[];
  weekly_rhythm: string;
}

/** The user's onboarding profile. */
export interface UserProfile {
  goal?: string;
  activity_level?: string;
  sleep_hours?: string;
  stress_level?: string;
  conditions?: string[];
  medications?: string[];
  allergies?: string[];
  diet?: string;
  time_available?: string;
  equipment?: string;
  [key: string]: unknown;
}

/** Metadata for an uploaded document. */
export interface DocRecord {
  id: number;
  filename: string;
  mime_type: string;
  uploaded_at: string;
}

/** Response from GET /onboarding-status. */
export interface OnboardingStatus {
  onboarded: boolean;
  profile: UserProfile | null;
  plan: WellnessPlan | null;
  doc_summary?: DocumentSummary | null;
  documents: DocRecord[];
}

/** Response from POST /upload-doc. */
export interface UploadDocResponse {
  status: "success" | "error";
  filename?: string;
  summary?: DocumentSummary;
  message?: string;
  /** Number of structured biomarker readings extracted (dashboard feature). */
  biomarkers_extracted?: number;
}

/**
 * Fetch the current user's onboarding status, profile, plan, and documents.
 */
export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  const token = await getToken();
  if (!token) throw new Error("Not authenticated");

  const res = await fetch(`${HTTP_BASE}/onboarding-status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch onboarding status: ${res.status}`);
  }
  return (await res.json()) as OnboardingStatus;
}

/**
 * Upload a health document (PDF or image) for processing.
 *
 * On web, the DocumentPicker asset has a `file` property (a native File object)
 * that can be used directly in FormData. On native, the asset has a `uri` that
 * we fetch as a blob first.
 */
export async function uploadDocument(
  asset: {
    uri: string;
    name: string;
    mimeType?: string;
    file?: File;
    base64?: string;
  },
): Promise<UploadDocResponse> {
  const token = await getToken();
  if (!token) throw new Error("Not authenticated");

  const formData = new FormData();

  // On web, the asset has a File object we can append directly.
  if (asset.file) {
    formData.append("file", asset.file, asset.name);
  } else if (asset.base64) {
    // Fallback: construct a blob from base64 (web without file object).
    const blob = base64ToBlob(asset.base64, asset.mimeType || "application/octet-stream");
    formData.append("file", blob, asset.name);
  } else {
    // Native: fetch the local URI as a blob and append it.
    const blobRes = await fetch(asset.uri);
    const blob = await blobRes.blob();
    formData.append("file", blob, asset.name);
  }

  const res = await fetch(`${HTTP_BASE}/upload-doc`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  return (await res.json()) as UploadDocResponse;
}

/** Convert a base64 string to a Blob. */
function base64ToBlob(base64: string, mimeType: string): Blob {
  const byteChars = atob(base64);
  const bytes = new Uint8Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) {
    bytes[i] = byteChars.charCodeAt(i);
  }
  return new Blob([bytes.buffer], { type: mimeType });
}

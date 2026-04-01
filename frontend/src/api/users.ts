import api from "./client";

// --- Types ---

export interface UserDetail {
  user_id: string;
  username: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
  updated_at: string;
  last_login?: string | null;
}

export interface UserCreateInput {
  username: string;
  full_name?: string;
  role: "admin" | "operator" | "viewer" | "reviewer" | "catalog_operator";
  password: string;
}

export interface UserUpdateInput {
  full_name?: string;
  role?: "admin" | "operator" | "viewer" | "reviewer" | "catalog_operator";
  is_active?: boolean;
}

// --- Admin CRUD ---

export async function listUsers(): Promise<{ items: UserDetail[] }> {
  return api.get("users").json<{ items: UserDetail[] }>();
}

export async function createUser(input: UserCreateInput): Promise<UserDetail> {
  return api.post("users", { json: input }).json<UserDetail>();
}

export async function updateUser(
  userId: string,
  input: UserUpdateInput,
): Promise<UserDetail> {
  return api.put(`users/${userId}`, { json: input }).json<UserDetail>();
}

export async function resetUserPassword(
  userId: string,
  newPassword: string,
): Promise<{ ok: boolean }> {
  return api
    .post(`users/${userId}/reset-password`, {
      json: { new_password: newPassword },
    })
    .json();
}

// --- Self-service ---

export async function updateProfile(
  fullName: string | null,
): Promise<{ user_id: string; full_name: string | null }> {
  return api.put("auth/profile", { json: { full_name: fullName } }).json();
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ ok: boolean }> {
  return api
    .post("auth/change-password", {
      json: { current_password: currentPassword, new_password: newPassword },
    })
    .json();
}

export async function forceChangePassword(
  newPassword: string,
): Promise<{ ok: boolean }> {
  return api
    .post("auth/force-change-password", {
      json: { new_password: newPassword },
    })
    .json();
}

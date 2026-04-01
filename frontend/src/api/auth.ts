import api from "./client";
import type { UserResponse } from "./types";

export interface LoginResult {
  logged_in: boolean;
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const formData = new URLSearchParams();
  formData.append("username", username);
  formData.append("password", password);
  return api.post("auth/login", { body: formData }).json<LoginResult>();
}

export async function logout(): Promise<void> {
  await api.post("auth/logout");
}

export async function getMe(): Promise<UserResponse> {
  return api.get("auth/me").json<UserResponse>();
}

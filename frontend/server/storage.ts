import { 
  type User, 
  type InsertUser,
  type UserDashboardPreferences,
  DEFAULT_DASHBOARD_PREFERENCES,
} from "@shared/schema";
import { randomUUID } from "crypto";

// modify the interface with any CRUD methods
// you might need

export interface IStorage {
  getUser(id: string): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  // Dashboard preferences
  getPreferences(userId: string): Promise<UserDashboardPreferences>;
  updatePreferences(userId: string, preferences: Partial<UserDashboardPreferences>): Promise<UserDashboardPreferences>;
}

export class MemStorage implements IStorage {
  private users: Map<string, User>;
  private preferences: Map<string, UserDashboardPreferences>;

  constructor() {
    this.users = new Map();
    this.preferences = new Map();
  }

  async getUser(id: string): Promise<User | undefined> {
    return this.users.get(id);
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    return Array.from(this.users.values()).find(
      (user) => user.username === username,
    );
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const id = randomUUID();
    const user: User = { ...insertUser, id };
    this.users.set(id, user);
    return user;
  }

  async getPreferences(userId: string): Promise<UserDashboardPreferences> {
    const prefs = this.preferences.get(userId);
    if (!prefs) {
      // Return deep copy of defaults
      return JSON.parse(JSON.stringify(DEFAULT_DASHBOARD_PREFERENCES));
    }
    return prefs;
  }

  async updatePreferences(
    userId: string, 
    updates: Partial<UserDashboardPreferences>
  ): Promise<UserDashboardPreferences> {
    const current = await this.getPreferences(userId);
    const merged: UserDashboardPreferences = {
      ...current,
      ...updates,
      // Deep merge for nested objects
      kpis: { ...current.kpis, ...(updates.kpis || {}) },
      assistant: { ...current.assistant, ...(updates.assistant || {}) },
      theme: { ...current.theme, ...(updates.theme || {}) },
      // Arrays are replaced entirely if provided
      widgets: updates.widgets ?? current.widgets,
      favorites: updates.favorites ?? current.favorites,
      frequently_used: updates.frequently_used ?? current.frequently_used,
    };
    this.preferences.set(userId, merged);
    return merged;
  }
}

export const storage = new MemStorage();

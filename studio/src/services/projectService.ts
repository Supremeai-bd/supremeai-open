// Project Spaces Service — ERR-B01 fix (canonical defect register 2026-09-15)
// বাংলা মন্তব্য: /projects পেজ আগে সম্পূর্ণ স্ট্যাটিক ছিল (ERR-B01) — "Create a
// project space" বাটন কিছুই করত না। এই সার্ভিস নতুন backend
// `/api/v1/projects` CRUD-এর সাথে পেজটিকে যুক্ত করে।

import { apiClient } from './apiClient';

export interface ProjectSpace {
  id: string;
  name: string;
  description: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProjectListResponse {
  items: ProjectSpace[];
  total: number;
}

export const projectService = {
  listProjects: async (): Promise<ProjectListResponse> => {
    return apiClient.get<ProjectListResponse>('/api/v1/projects');
  },

  createProject: async (input: { name: string; description?: string }): Promise<ProjectSpace> => {
    const res = await apiClient.post<{ status: string; project: ProjectSpace }>(
      '/api/v1/projects',
      { name: input.name, description: input.description ?? '' },
    );
    return res.project;
  },

  renameProject: async (projectId: string, name: string): Promise<ProjectSpace> => {
    const res = await apiClient.patch<{ status: string; project: ProjectSpace }>(
      `/api/v1/projects/${projectId}`,
      { name },
    );
    return res.project;
  },

  deleteProject: async (projectId: string): Promise<void> => {
    await apiClient.delete<{ status: string; message: string }>(
      `/api/v1/projects/${projectId}`,
    );
  },
};

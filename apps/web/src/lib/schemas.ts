import { z } from "zod";

export const registerSchema = z.object({
  full_name: z.string().trim().min(2, "Enter your full name"),
  email: z.string().trim().email("Enter a valid work email"),
  password: z.string().min(10, "At least 10 characters").regex(/\d/, "Include a digit").regex(/[a-zA-Z]/, "Include a letter"),
  organisation_name: z.string().trim().min(2, "Organisation name is required"),
  industry: z.string().trim().max(120).optional(),
  company_size: z.string().optional(),
  website: z.string().trim().max(300).optional(),
  job_title: z.string().trim().max(120).optional(),
});

// FrR2 Storage API

import { apiClient } from './apiClient';

export const uploadFileToR2 = async (file: File) => {
    try {
        // বাংলা মন্তব্য: ১. ব্যাকএন্ড থেকে প্রে-সাইন্ড আপলোড ইউআরএল নিয়ে আসা
        // Issue #2522: raw fetch -> apiClient.post — manual Authorization হেডার আর দরকার নেই,
        // timeout/queue/error-mapping ক্লায়েন্ট নিজেই দেয়।
        const { upload_url, file_path } = await apiClient.post<{ upload_url: string; file_path: string }>(
            '/api/v1/media/generate-upload-url',
            { file_name: file.name, file_type: file.type, folder: 'custom_skills' },
        );

        // বাংলা মন্তব্য: ২. সরাসরি Cloudflare R2-তে ফাইল আপলোড (ব্যাকএন্ড বাইপাস করে)
        // Justified raw fetch (Issue #2522): এটি আমাদের backend API নয় — pre-signed
        // external storage URL; apiClient-এর auth/retry/base-URL এখানে প্রযোজ্য নয়।
        const uploadResponse = await fetch(upload_url, {
            method: 'PUT',
            headers: {
                'Content-Type': file.type,
            },
            body: file
        });

        if (!uploadResponse.ok) {
            throw new Error('Failed to upload file directly to R2');
        }

        // বাংলা মন্তব্য: ৩. সফল হলে ফাইলের পাথ রিটার্ন করা (যা Supabase ডাটাবেসে সেভ হবে)
        return file_path;

    } catch (error) {
        console.error('Upload Error:', error);
        throw error;
    }
};

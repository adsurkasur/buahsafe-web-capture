import os
import sys
import glob
import traceback

def main():
    print("=" * 60)
    print("       BUAHSAFE: AUTOMATED END-TO-END SPECTRAL EDA        ")
    print("=" * 60)

    # 1. Menentukan Direktori Kerja (Tempat skrip ini berada)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    # 2. Mencari File Dataset Excel
    excel_files = glob.glob(os.path.join(base_dir, "*.xlsx"))
    if not excel_files:
        raise FileNotFoundError("Tidak ditemukan file .xlsx di folder ini!")

    # Prioritaskan file gabungan jika ada
    target_file = None
    for f in excel_files:
        if "gabungan" in os.path.basename(f).lower():
            target_file = f
            break
    if not target_file:
        target_file = excel_files[0]

    print(f"\n[INFO] Membaca dataset: {os.path.basename(target_file)}")

    # 3. Import Library Analisis
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    from scipy import stats
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    # Direktori Output
    output_dir = os.path.join(base_dir, "eda_buahsafe_output")
    os.makedirs(output_dir, exist_ok=True)

    # 6 Kanal Utama Sensor AS7263
    target_channels = ['nm610', 'nm680', 'nm730', 'nm760', 'nm810', 'nm860']
    wavelengths = [610, 680, 730, 760, 810, 860]

    df_raw = pd.read_excel(target_file)
    print(f"[DATA] Total baris mentah: {len(df_raw)}")
    print(f"[DATA] Sampel per kelas: {dict(df_raw['label'].value_counts())}")

    # 4. Deteksi Outlier Ekstrem (3.0 * IQR)
    print("\n[PROSES 1/5] Mendeteksi dan memfilter lonjakan outlier ekstrem...")
    outlier_indices = set()
    outlier_logs = []

    for col in target_channels:
        q25 = df_raw[col].quantile(0.25)
        q75 = df_raw[col].quantile(0.75)
        iqr = q75 - q25
        upper_limit = q75 + 3.0 * iqr
        
        spikes = df_raw[df_raw[col] > upper_limit]
        for idx, row in spikes.iterrows():
            outlier_indices.add(idx)
            outlier_logs.append({
                'excel_row': idx + 2,
                'fruit_id': row['fruit_id'],
                'label': row['label'],
                'rotasi': row['rotasi_buah'],
                'scan_no': row['scan_no'],
                'kanal_pemicu': col,
                'nilai': row[col],
                'ambang_batas': upper_limit
            })

    df_outliers = pd.DataFrame(outlier_logs).drop_duplicates(subset=['excel_row'])
    df_outliers.to_csv(os.path.join(output_dir, "log_outlier_ekstrem.csv"), index=False)
    print(f"[INFO] Terdeteksi {len(outlier_indices)} titik spike/outlier ekstrem.")

    # Dataset Bersih
    df_clean = df_raw.drop(index=list(outlier_indices)).copy()
    print(f"[INFO] Sisa data bersih: {len(df_clean)} data (Anomali: {(df_clean['label']=='anomali').sum()}, Normal: {(df_clean['label']=='normal').sum()})")

    # 5. Uji Statistik & Effect Size
    print("\n[PROSES 2/5] Menghitung uji beda nyata & effect size...")
    stat_records = []
    for col, wl in zip(target_channels, wavelengths):
        norm = df_clean[df_clean['label'] == 'normal'][col]
        anom = df_clean[df_clean['label'] == 'anomali'][col]
        
        t_stat, p_welch = stats.ttest_ind(norm, anom, equal_var=False)
        u_stat, p_mann = stats.mannwhitneyu(norm, anom)
        
        # Cohen's d
        n1, n2 = len(norm), len(anom)
        s_pooled = np.sqrt(((n1 - 1)*norm.var(ddof=1) + (n2 - 1)*anom.var(ddof=1)) / (n1 + n2 - 2))
        cohens_d = (norm.mean() - anom.mean()) / s_pooled
        
        stat_records.append({
            'Kanal': col,
            'Wavelength (nm)': wl,
            'Mean Normal': round(norm.mean(), 2),
            'Std Normal': round(norm.std(), 2),
            'Mean Anomali': round(anom.mean(), 2),
            'Std Anomali': round(anom.std(), 2),
            'Selisih (Norm-Anom)': round(norm.mean() - anom.mean(), 2),
            'p-value (t-test)': f"{p_welch:.4e}",
            'Signifikan (p<0.05)': "Ya" if p_welch < 0.05 else "Tidak",
            "Cohen's d": round(cohens_d, 2)
        })

    df_stats = pd.DataFrame(stat_records)
    df_stats.to_csv(os.path.join(output_dir, "ringkasan_uji_statistik.csv"), index=False)
    print(df_stats.to_string(index=False))

    # 6. Ekstraksi Fitur Rasio Spektral
    print("\n[PROSES 3/5] Menghitung fitur indeks spektral...")
    df_clean['ratio_810_680'] = df_clean['nm810'] / (df_clean['nm680'] + 1e-5)
    df_clean['ratio_730_680'] = df_clean['nm730'] / (df_clean['nm680'] + 1e-5)
    df_clean['ratio_860_810'] = df_clean['nm860'] / (df_clean['nm810'] + 1e-5)
    df_clean['red_edge_slope'] = (df_clean['nm730'] - df_clean['nm680']) / (730 - 680)
    df_clean['ndvi_like'] = (df_clean['nm810'] - df_clean['nm680']) / (df_clean['nm810'] + df_clean['nm680'] + 1e-5)

    df_clean.to_csv(os.path.join(output_dir, "buahsafe_dataset_cleaned_featured.csv"), index=False)

    # 7. Analisis Variansi Rotasi Intra-Buah
    print("\n[PROSES 4/5] Menghitung variansi intra-buah...")
    fruit_var = df_clean.groupby(['fruit_id', 'label'])[target_channels].std().reset_index()

    # 8. Visualisasi Grafik (4 Panel)
    print("\n[PROSES 5/5] Merender grafik publikasi 300 DPI...")
    fig, axes = plt.subplots(2, 2, figsize=(15, 11))
    sns.set_theme(style="whitegrid")

    palette = {'normal': '#2ca02c', 'anomali': '#d62728'}

    # Panel A: Spectral Signature Curve
    norm_means = [df_clean[df_clean['label'] == 'normal'][col].mean() for col in target_channels]
    norm_stds = [df_clean[df_clean['label'] == 'normal'][col].std() for col in target_channels]
    anom_means = [df_clean[df_clean['label'] == 'anomali'][col].mean() for col in target_channels]
    anom_stds = [df_clean[df_clean['label'] == 'anomali'][col].std() for col in target_channels]

    axes[0, 0].plot(wavelengths, norm_means, 'o-', color=palette['normal'], label='Normal (Sehat)', linewidth=2.5)
    axes[0, 0].fill_between(wavelengths, np.array(norm_means) - np.array(norm_stds), np.array(norm_means) + np.array(norm_stds), color=palette['normal'], alpha=0.2)

    axes[0, 0].plot(wavelengths, anom_means, 's-', color=palette['anomali'], label='Anomali (Rusak)', linewidth=2.5)
    axes[0, 0].fill_between(wavelengths, np.array(anom_means) - np.array(anom_stds), np.array(anom_means) + np.array(anom_stds), color=palette['anomali'], alpha=0.2)

    axes[0, 0].set_title('A. Profil Kurva Spektral (Mean ± 1 SD)', fontsize=12, fontweight='bold')
    axes[0, 0].set_xlabel('Panjang Gelombang (nm)', fontsize=10)
    axes[0, 0].set_ylabel('Intensitas Pantulan Optik', fontsize=10)
    axes[0, 0].set_xticks(wavelengths)
    axes[0, 0].legend(loc='upper left')

    # Panel B: Boxplot 6 Kanal
    melted_df = df_clean.melt(id_vars=['label'], value_vars=target_channels, var_name='Kanal', value_name='Intensitas')
    sns.boxplot(ax=axes[0, 1], data=melted_df, x='Kanal', y='Intensitas', hue='label', palette=palette)
    axes[0, 1].set_title('B. Sebaran Nilai 6 Kanal Spektral', fontsize=12, fontweight='bold')
    axes[0, 1].set_xlabel('Kanal Sensor', fontsize=10)
    axes[0, 1].set_ylabel('Intensitas', fontsize=10)

    # Panel C: Variansi Intra-Buah (Kanal 810 nm)
    sns.boxplot(ax=axes[1, 0], data=fruit_var, x='label', y='nm810', palette=palette)
    axes[1, 0].set_title('C. Variansi Rotasi Intra-Buah (nm810)', fontsize=12, fontweight='bold')
    axes[1, 0].set_xlabel('Kondisi Buah', fontsize=10)
    axes[1, 0].set_ylabel('Std Dev Rotasi per Buah', fontsize=10)

    # Panel D: PCA Score Plot
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df_clean[target_channels])
    pca = PCA(n_components=2)
    X_pca = pca.fit_transform(X_scaled)
    df_clean['pca1'] = X_pca[:, 0]
    df_clean['pca2'] = X_pca[:, 1]

    sns.scatterplot(ax=axes[1, 1], data=df_clean, x='pca1', y='pca2', hue='label', palette=palette, alpha=0.85, s=60)
    axes[1, 1].set_title(f'D. PCA Biplot (PC1: {pca.explained_variance_ratio_[0]*100:.1f}%, PC2: {pca.explained_variance_ratio_[1]*100:.1f}%)', fontsize=12, fontweight='bold')
    axes[1, 1].set_xlabel('Principal Component 1', fontsize=10)
    axes[1, 1].set_ylabel('Principal Component 2', fontsize=10)

    plt.tight_layout()
    plot_path = os.path.join(output_dir, "eda_buahsafe_summary_plot.png")
    plt.savefig(plot_path, dpi=300)
    plt.close()

    print(f"\n[SUKSES] Seluruh file analisis tersimpan di: {output_dir}")
    print(f"[SUKSES] Gambar grafik: {os.path.basename(plot_path)}")

    # Membuka folder output otomatis di Windows Explorer
    if sys.platform.startswith('win'):
        os.startfile(output_dir)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\n" + "!" * 60)
        print("TERJADI KESALAHAN SAAT MENJALANKAN SKRIP:")
        print("!" * 60)
        traceback.print_exc()
    finally:
        # Menjaga jendela command prompt tetap terbuka saat di-double click
        print("\n" + "-" * 60)
        input("Tekan [ENTER] untuk menutup jendela ini...")
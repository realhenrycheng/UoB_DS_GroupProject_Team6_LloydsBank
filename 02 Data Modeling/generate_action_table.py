import pandas as pd
import numpy as np
import os


def load_and_clean_data():
    print("📥 Reading and cleaning underlying data...")
    df_ns = pd.read_csv('news_score.csv')
    df_hr = pd.read_csv('hiring_100k.csv')
    df_fw = pd.read_csv('forward_scores_v3.csv', low_memory=False)
    df_fc = pd.read_csv('financial_company_context.csv', encoding='cp1252', low_memory=False)

    df_fc = df_fc.loc[:, ~df_fc.columns.str.startswith('Unnamed:')]
    df_fc.rename(columns={'CompanyNumber_norm': 'CompanyNumber'}, inplace=True)

    for df in [df_fc, df_fw, df_ns, df_hr]:
        df['CompanyNumber'] = df['CompanyNumber'].astype(str).str.strip()

    print("🔗 Merging data into a wide table...")
    df_merged = df_fc.merge(df_fw, on='CompanyNumber', how='left')
    df_merged = df_merged.merge(df_ns[['CompanyNumber', 'final_news_score', 'sentiment_direction']], on='CompanyNumber',
                                how='left')
    df_merged = df_merged.merge(df_hr[['CompanyNumber', 'company_hiring_score']], on='CompanyNumber', how='left')

    return df_merged


def get_percentile_label(val, is_fraction=True, short_mode=False):
    if pd.isna(val):
        return None if short_mode else "[Data Missing]"

    p = val * 100 if is_fraction else val

    if p >= 95:
        return "Top 5%" if short_mode else "[Top 5% Tier]"
    elif p >= 85:
        return "5-15%" if short_mode else "[5%-15% Tier]"
    elif p >= 75:
        return "15-25%" if short_mode else "[15%-25% Tier]"
    elif p >= 50:
        return "25-50%" if short_mode else "[25%-50% Tier]"
    else:
        return "50-100%" if short_mode else "[50%-100% Tier]"


def get_primary_action_category(row):
    f_d_stat = str(row.get('forward_deepen_status')).strip().title()
    f_g_stat = str(row.get('forward_relative_grow_status')).strip().title()
    f_df_stat = str(row.get('forward_defend_status')).strip().title()

    has_complete_forward = (f_d_stat == 'Complete') or (f_g_stat == 'Complete') or (f_df_stat == 'Complete')

    if not has_complete_forward:
        return "Insufficient Forward Evidence"

    active_tiers = ["Top 5%", "5-15%", "15-25%", "25-50%"]

    d_p = get_percentile_label(row.get('forward_deepen_reference_percentile'), is_fraction=True, short_mode=True)
    g_p = get_percentile_label(row.get('forward_relative_grow_reference_percentile'), is_fraction=True, short_mode=True)
    df_p = get_percentile_label(row.get('forward_defend_reference_percentile'), is_fraction=True, short_mode=True)

    has_opp = (f_d_stat == 'Complete' and d_p in active_tiers) or (f_g_stat == 'Complete' and g_p in active_tiers)
    has_press = (f_df_stat == 'Complete' and df_p in active_tiers)

    if has_opp and not has_press:
        return "Opportunity without Pressure"
    elif not has_opp and has_press:
        return "Pressure Only"
    elif has_opp and has_press:
        return "Opportunity with Pressure"
    else:
        return "No Active Forward Signal"


def generate_business_scenario(row):
    tags = []
    active_tiers = ["Top 5%", "5-15%", "15-25%", "25-50%"]

    static_status = str(row.get('calibration_status')).strip().upper()
    if static_status == 'THREE_WAY_COMPLETE':
        static_tier = get_percentile_label(row.get('priority_queue_percentile'), is_fraction=False, short_mode=True)
        if static_tier and static_tier != '[Data Missing]':
            tags.append(f"Current Priority [{static_tier}]")

    f_d_stat = str(row.get('forward_deepen_status')).strip().title()
    f_g_stat = str(row.get('forward_relative_grow_status')).strip().title()
    f_df_stat = str(row.get('forward_defend_status')).strip().title()

    has_complete_forward = (f_d_stat == 'Complete') or (f_g_stat == 'Complete') or (f_df_stat == 'Complete')

    deepen_tier = get_percentile_label(row.get('forward_deepen_reference_percentile'), is_fraction=True,
                                       short_mode=True)
    if deepen_tier in active_tiers and f_d_stat == 'Complete':
        tags.append(f"Deepen [{deepen_tier}]")

    grow_tier = get_percentile_label(row.get('forward_relative_grow_reference_percentile'), is_fraction=True,
                                     short_mode=True)
    if grow_tier in active_tiers and f_g_stat == 'Complete':
        tags.append(f"Grow [{grow_tier}]")

    defend_tier = get_percentile_label(row.get('forward_defend_reference_percentile'), is_fraction=True,
                                       short_mode=True)
    if defend_tier in active_tiers and f_df_stat == 'Complete':
        tags.append(f"Risk [{defend_tier}]")

    if not tags:
        if not has_complete_forward:
            return "Insufficient Forward Evidence"
        else:
            return "No Strong Forward Signal"

    return " | ".join(tags)


def generate_explanation(row):
    static_status = str(row.get('calibration_status')).strip().upper()

    if static_status == 'THREE_WAY_COMPLETE':
        s_tier = get_percentile_label(row.get('priority_queue_percentile'), is_fraction=False, short_mode=False)

        p_dim = row.get('primary_dimension_calibrated')
        s_dim = "Primary financial direction unavailable" if pd.isna(p_dim) else str(p_dim).title()

        c_name = row.get('cluster_name_auto')
        s_cluster = "Financial profile unavailable" if pd.isna(c_name) else str(c_name)

        static_text = f"[Static Financial Signal] The enterprise's current financial signal priority is in the {s_tier}, primarily driven by the {s_dim} dimension, corresponding to the '{s_cluster}' profile."
    elif static_status == 'PARTIAL_DIMENSION_ONLY':
        static_text = "[Static Financial Signal] Partial financial evidence; unable to evaluate full static priority."
    else:
        static_text = "[Static Financial Signal] Insufficient financial evidence; unable to evaluate current status."

    forward_desc = []
    f_d_stat = str(row.get('forward_deepen_status')).strip().title()
    f_g_stat = str(row.get('forward_relative_grow_status')).strip().title()
    f_df_stat = str(row.get('forward_defend_status')).strip().title()

    if f_d_stat == 'Complete':
        d_tier = get_percentile_label(row.get('forward_deepen_reference_percentile'), is_fraction=True,
                                      short_mode=False)
        forward_desc.append(f"Deepen expansion momentum is in the {d_tier}")

    if f_g_stat == 'Complete':
        g_tier = get_percentile_label(row.get('forward_relative_grow_reference_percentile'), is_fraction=True,
                                      short_mode=False)
        if g_tier == "[25%-50% Tier]":
            forward_desc.append(f"Relative Grow requirement is in the {g_tier} (Reserve Observation)")
        else:
            forward_desc.append(f"Relative Grow requirement is in the {g_tier}")

    if f_df_stat == 'Complete':
        df_p = row.get('forward_defend_reference_percentile')
        df_tier = get_percentile_label(df_p, is_fraction=True, short_mode=False)
        if not pd.isna(df_p) and df_p >= 0.5:
            forward_desc.append(f"Defend pressure is in the {df_tier}, indicating a signal for further verification")
        else:
            forward_desc.append("no strong Defend signal was detected")

    if forward_desc:
        forward_text = "[Future Forward Signals] " + "; ".join(forward_desc) + "."
        if f_g_stat == 'Complete' and float(row.get('forward_relative_grow_tail_signal') or 0) > 0:
            forward_text += " Additionally, a potential funding-need signal was captured; verification is recommended."
    else:
        forward_text = "[Future Forward Signals] Insufficient forward evidence; automatic prediction generation terminated."

    news_val = row.get('final_news_score')
    news_dir = str(row.get('sentiment_direction')).strip().lower()
    hire_val = row.get('company_hiring_score')
    news = float(news_val) if not pd.isna(news_val) else 0.0
    hire = float(hire_val) if not pd.isna(hire_val) else 50.0

    ext_patches = []
    if news > 70 and news_dir == 'positive':
        ext_patches.append("strong positive media sentiment")
    elif news > 70 and news_dir == 'negative':
        ext_patches.append("severe negative media sentiment")

    if hire > 75:
        ext_patches.append("signs of personnel expansion")
    elif hire < 20:
        ext_patches.append("personnel hiring contraction")

    if ext_patches:
        ext_text = "[External Validation Signals] " + ", and ".join(ext_patches) + "."
    else:
        ext_text = ""

    disclaimer = " Note: Results are for business screening and do not replace client due diligence or formal credit assessment."

    final_text = f"{static_text} {forward_text} {ext_text}".strip() + disclaimer
    return final_text.replace("  ", " ")


def main():
    df = load_and_clean_data()
    print("⚙️ Executing rule engine to generate multi-level scenarios and business suggestion text...")

    df['Primary_Action_Category'] = df.apply(get_primary_action_category, axis=1)
    df['Business_Scenario'] = df.apply(generate_business_scenario, axis=1)
    df['Explanation_Text'] = df.apply(generate_explanation, axis=1)

    display_columns = [
        'CompanyNumber', 'CompanyName', 'primary_sector_x',
        'priority_calibrated', 'priority_queue_percentile', 'primary_dimension_calibrated', 'cluster_name_auto',
        'calibration_status',
        'forward_deepen_score', 'forward_deepen_reference_percentile', 'forward_deepen_status',
        'forward_relative_grow_score', 'forward_relative_grow_reference_percentile',
        'forward_relative_grow_tail_signal', 'forward_relative_grow_status',
        'forward_defend_score', 'forward_defend_reference_percentile', 'forward_defend_status',
        'final_news_score', 'sentiment_direction', 'company_hiring_score',
        'Primary_Action_Category', 'Business_Scenario', 'Explanation_Text'
    ]

    df_final = df[[col for col in display_columns if col in df.columns]]
    output_filename = 'Final_Strategic_Business.csv'

    print(f"🧹 Exporting final data to {output_filename} ...")
    df_final.to_csv(output_filename, index=False, encoding='utf-8-sig')


if __name__ == "__main__":
    main()
"""
Used to extract samples from cleaned Companies House,

Two sampling methods:
1. sample_by_sector_equal()  -Extract the same for each sector
2. sample_by_sector_proportional() -Extract by the proportion of each sector in the total
"""

import pandas as pd

RANDOM_STATE = 6

def sample_by_sector_equal(
    csv_path: str,
    total_sample_size: int,
    sector_col: str = "primary_sector",
    random_state: int = RANDOM_STATE,
) -> pd.DataFrame:
    """
    If the actual number of companies in a sector is less than the average number, 
    all companies in the sector are taken out.

    Parameters
    ----------
    csv_path : str
        Companies House CSV path
    total_sample_size : int
        The expected total sample size
    sector_col : str
        sector field name, default is "primary_sector"
    random_state : int
        random seed

    Returns
    -------
    pd.DataFrame
        In addition to sampling results, there is a new column 'sample_method' marked 'equal'.
    """
    df = pd.read_csv(csv_path)

    total_n = len(df)
    if total_n == 0:
        raise ValueError("Table is empty")

    sectors = df[sector_col].dropna().unique()
    n_sectors = len(sectors)
    if n_sectors == 0:
        raise ValueError(f"No sector value was found in the column '{sector_col}'")

    per_sector_target = total_sample_size // n_sectors
    remainder = total_sample_size % n_sectors

    samples = []
    shortage_report = []

    for i, sector in enumerate(sectors):
        sector_df = df[df[sector_col] == sector]
        target_n = per_sector_target + (1 if i < remainder else 0)

        if len(sector_df) < target_n:
            # There are not enough companies in this sector, all companies are taken out
            sampled = sector_df.copy()
            shortage_report.append((sector, len(sector_df), target_n))
        else:
            sampled = sector_df.sample(n=target_n, random_state=random_state)

        samples.append(sampled)

    result = pd.concat(samples, ignore_index=True)
    result["sample_method"] = "equal"

    if shortage_report:
        print("The actual number of companies in the following sectors is insufficient, and all have been taken out:")
        for sector, actual, target in shortage_report:
            print(f"  - {sector}: actual {actual} < expected {target}")

    print(f"\nSampling complete. Target total: {total_sample_size}, Actual: {len(result)}")
    print(result[sector_col].value_counts())

    return result


def sample_by_sector_proportional(
    csv_path: str,
    total_sample_size: int,
    sector_col: str = "primary_sector",
    random_state: int = 42,
) -> pd.DataFrame:
    """
    Sampling by sector proportion: 
        Keep the sector distribution of the sampled results consistent with the original population.

    Parameters
    ----------
    csv_path : str
        Companies House CSV path
    total_sample_size : int
        The expected total sample size
    sector_col : str
        sector field name, default is "primary_sector"
    random_state : int
        random seed

    Returns
    -------
    pd.DataFrame
        In addition to sampling results, there is a new column 'sample_method' marked 'proportional'.
    """
    df = pd.read_csv(csv_path)

    total_n = len(df)
    if total_n == 0:
        raise ValueError("Table is empty")

    sector_counts = df[sector_col].value_counts()
    sector_proportions = sector_counts / total_n

    samples = []
    zero_report = []

    for sector, proportion in sector_proportions.items():
        sector_df = df[df[sector_col] == sector]

        target_n = int(total_sample_size * proportion + 0.5)
        target_n = min(target_n, len(sector_df))  # Not more than the actual number of  the sector

        if target_n > 0:
            sampled = sector_df.sample(n=target_n, random_state=random_state)
            samples.append(sampled)
        else:
            zero_report.append((sector, proportion))

    if zero_report:
        print("The following sectors are too small to be sampled proportionally (rounded to zero):")
        for sector, proportion in zero_report:
            print(f"  - {sector}: {proportion:.4%}")

    result = pd.concat(samples, ignore_index=True)
    result["sample_method"] = "proportional"

    print(f"Sampling complete. Target total: {total_sample_size}, Actual: {len(result)}")
    print(result[sector_col].value_counts())
    print("\nOriginal vs sampled:")
    comparison = pd.DataFrame({
        "Original": sector_proportions,
        "sampled": result[sector_col].value_counts() / len(result),
    })
    print(comparison)

    return result
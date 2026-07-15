# Companies House Data Dictionary

> Source: Companies House Bulk Data Export

------

# Company Information（公司基础信息）

| Field             | English Description                                          | 中文说明                                  |
| ----------------- | ------------------------------------------------------------ | ----------------------------------------- |
| CompanyName       | Registered company name.                                     | 公司注册名称。                            |
| CompanyNumber     | Unique Companies House company identifier.                   | Companies House 分配的唯一公司编号。      |
| CompanyCategory   | Legal form of the company (e.g., Private Limited Company, LLP, CIC). | 公司法律类型（如有限公司、LLP、CIC 等）。 |
| CompanyStatus     | Current company status.                                      | 公司当前状态。                            |
| CountryOfOrigin   | Jurisdiction of origin reported by Companies House.          | Companies House 记录的注册司法辖区。      |
| IncorporationDate | Date the company was incorporated.                           | 公司成立日期。                            |
| DissolutionDate   | Date the company was dissolved, if applicable.               | 公司注销日期（如适用）。                  |
| URI               | Companies House resource URI for the company record.         | Companies House 公司记录对应的资源 URI。  |

------

# Registered Address（注册地址）

| Field                   | English Description                               | 中文说明                   |
| ----------------------- | ------------------------------------------------- | -------------------------- |
| RegAddress_CareOf       | Care-of recipient line in the registered address. | 注册地址中的代收人信息。   |
| RegAddress_POBox        | PO Box number in the registered address.          | 注册地址中的邮政信箱号码。 |
| RegAddress_AddressLine1 | First line of the registered address.             | 注册地址第一行。           |
| RegAddress_AddressLine2 | Second line of the registered address.            | 注册地址第二行。           |
| RegAddress_PostTown     | Registered post town or locality.                 | 注册所在地城市。           |
| RegAddress_County       | County or region.                                 | 郡、行政区或地区。         |
| RegAddress_Country      | Country of the registered address.                | 注册地址所属国家。         |
| RegAddress_PostCode     | Postal code of the registered address.            | 邮政编码。                 |

------

# Accounts Information（财务申报信息）

| Field                    | English Description                                          | 中文说明                                                     |
| ------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| Accounts_AccountRefDay   | Accounting reference day.                                    | 会计年度截止日（日）。                                       |
| Accounts_AccountRefMonth | Accounting reference month.                                  | 会计年度截止月（月）。                                       |
| Accounts_NextDueDate     | Next accounts filing due date.                               | 下一次财务报表提交截止日期。                                 |
| Accounts_LastMadeUpDate  | Last accounts made-up date.                                  | 最近一次财务报表截止日期。                                   |
| Accounts_AccountCategory | Companies House accounting classification (e.g., Micro Entity, Small, Full Accounts). | Companies House 会计分类（如 Micro Entity、Small、Full Accounts）。 |

------

# Confirmation Statement / Returns（确认声明信息）

| Field                  | English Description                               | 中文说明                                            |
| ---------------------- | ------------------------------------------------- | --------------------------------------------------- |
| Returns_NextDueDate    | Next return or confirmation-related due date.     | 下一次 Return / Confirmation Statement 截止日期。   |
| Returns_LastMadeUpDate | Last return or confirmation-related made-up date. | 最近一次 Return / Confirmation Statement 截止日期。 |
| ConfStmtNextDueDate    | Next Confirmation Statement due date.             | 下一次 Confirmation Statement 截止日期。            |
| ConfStmtLastMadeUpDate | Last Confirmation Statement made-up date.         | 最近一次 Confirmation Statement 截止日期。          |

------

# Mortgage Information（抵押登记信息）

| Field                          | English Description                             | 中文说明                 |
| ------------------------------ | ----------------------------------------------- | ------------------------ |
| Mortgages_NumMortCharges       | Total number of mortgage charges registered.    | 已登记抵押权总数。       |
| Mortgages_NumMortOutstanding   | Number of outstanding mortgage charges.         | 当前未解除的抵押权数量。 |
| Mortgages_NumMortPartSatisfied | Number of partially satisfied mortgage charges. | 部分解除的抵押权数量。   |
| Mortgages_NumMortSatisfied     | Number of satisfied mortgage charges.           | 已解除的抵押权数量。     |

------

# Industry Classification（行业分类信息）

| Field             | English Description                                          | 中文说明                                        |
| ----------------- | ------------------------------------------------------------ | ----------------------------------------------- |
| SICCode_SicText_1 | Primary SIC code and description supplied by Companies House. | Companies House 提供的第一行业 SIC 编码及描述。 |
| SICCode_SicText_2 | Secondary SIC code and description.                          | 第二行业 SIC 编码及描述。                       |
| SICCode_SicText_3 | Third SIC code and description.                              | 第三行业 SIC 编码及描述。                       |
| SICCode_SicText_4 | Fourth SIC code and description.                             | 第四行业 SIC 编码及描述。                       |

### Notes

A company may report up to four SIC (Standard Industrial Classification) codes. Each SIC code represents a business activity undertaken by the company. Multiple SIC codes are retained and used during industry classification to avoid losing information from diversified companies.

一家企业最多可申报 4 个 SIC（Standard Industrial Classification）行业代码。每个 SIC 代表企业从事的一项业务活动。本项目保留全部 SIC 代码进行行业分类，而非仅使用第一 SIC，以减少多元化企业的信息损失。

------

# Limited Partnership Information（有限合伙企业信息）

| Field                              | English Description         | 中文说明         |
| ---------------------------------- | --------------------------- | ---------------- |
| LimitedPartnerships_NumGenPartners | Number of general partners. | 普通合伙人数量。 |
| LimitedPartnerships_NumLimPartners | Number of limited partners. | 有限合伙人数量。 |

------

# Previous Company Names（历史名称）

| Field                      | English Description                                        | 中文说明               |
| -------------------------- | ---------------------------------------------------------- | ---------------------- |
| PreviousName_X_CONDATE     | Effective date when the previous company name was adopted. | 历史公司名称生效日期。 |
| PreviousName_X_CompanyName | Historical company name.                                   | 历史公司名称。         |

其中：

```text
X = 1 ... 10
```

表示最多保留 10 次历史名称记录。

------

# Common Company Status Values（常见公司状态）

| Status                          | 中文解释   |
| ------------------------------- | ---------- |
| Active                          | 正常运营   |
| Active - Proposal to Strike Off | 已申请注销 |
| Liquidation                     | 清算中     |
| Administration                  | 托管重整中 |
| Dissolved                       | 已注销     |
| Receivership                    | 接管中     |

------

# Common Company Categories（常见公司类型）

| Category                      | 中文解释                |
| ----------------------------- | ----------------------- |
| Private Limited Company       | 私人有限公司（Ltd）     |
| Limited Liability Partnership | 有限责任合伙企业（LLP） |
| Community Interest Company    | 社区利益公司（CIC）     |
| Public Limited Company        | 上市公众有限公司（PLC） |
| Private Unlimited Company     | 无限责任公司            |


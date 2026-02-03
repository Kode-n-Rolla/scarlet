# SCARLET Index Report

## Directory
`/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith`

## Files
- `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Coin.sol`
- `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Factory.sol`
- `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/InterestModel.sol`
- `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Lender.sol`
- `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Lens.sol`
- `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Vault.sol`

## Contracts
### Coin (contract)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Coin.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `burn(uint256)` [external] — line 19
- `mint(address,uint256)` [external] — line 14
- `DOMAIN_SEPARATOR() returns (bytes32)` [public] — line 162
- `approve(address,uint256) returns (bool)` [public] — line 68
- `constructor(address,string,string)` [public] — line 10
- `permit(address,address,uint256,uint256,uint8,bytes32,bytes32)` [public] — line 116
- `transfer(address,uint256) returns (bool)` [public] — line 76
- `transferFrom(address,address,uint256) returns (bool)` [public] — line 90

### CoinDeployer (library)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Factory.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `deployCoin(address,uint256,bytes)` [external] — line 53
- `getAddress(address,uint256) returns (address)` [external] — line 49

### Factory (contract)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Factory.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `acceptOperator()` [external] — line 92
- `deploy(Factory.DeployParams) returns (address, address, address)` [external] — line 149
- `deploymentsLength() returns (uint256)` [external] — line 83
- `getFeeOf(address) returns (uint256)` [external] — line 116
- `pullReserves(address)` [external] — line 122
- `setCustomFeeBps(address,uint256) onlyOperator` [external] — line 110
- `setFeeBps(uint256) onlyOperator` [external] — line 104
- `setFeeRecipient(address) onlyOperator` [external] — line 99
- `setPendingOperator(address) onlyOperator` [external] — line 87
- `constructor(address,uint256)` [public] — line 72

### InterestModelDeployer (library)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Factory.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `deploy() returns (address)` [external] — line 11

### LenderDeployer (library)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Factory.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `deployLender(address,uint256,bytes)` [external] — line 25
- `getAddress(address,uint256) returns (address)` [external] — line 21

### VaultDeployer (library)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Factory.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `deployVault(address,uint256,bytes)` [external] — line 39
- `getAddress(address,uint256) returns (address)` [external] — line 35

### InterestModel (contract)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/InterestModel.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `calculateInterest(uint256,uint256,uint256,uint256,uint256,uint256,uint256) returns (uint256, uint256)` [external] — line 20

### IChainlinkFeed (interface)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Lender.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `decimals() returns (uint8)` [external] — line 13
- `latestRoundData() returns (uint80, int256, uint256, uint256, uint80)` [external] — line 14

### IFactory (interface)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Lender.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `getFeeOf(address) returns (uint256)` [external] — line 24
- `minDebtFloor() returns (uint256)` [external] — line 25

### Lender (contract)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Lender.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `acceptOperator()` [external] — line 959
- `adjust(address,int256,int256,bool)` [external] — line 325
- `buy(uint256,uint256) beforeDeadline returns (uint256)` [external] — line 521
- `delegate(address,bool)` [external] — line 333
- `enableImmutabilityNow() onlyOperator beforeDeadline` [external] — line 970
- `getFeedPrice() returns (uint256, uint256)` [external] — line 748
- `getPendingInterest() returns (uint256)` [external] — line 881
- `liquidate(address,uint256,uint256) returns (uint256)` [external] — line 368
- `pullGlobalReserves(address)` [external] — line 983
- `pullLocalReserves() onlyOperator` [external] — line 975
- `reapprovePsmVault() beforeDeadline` [external] — line 545
- `redeem(uint256,uint256) returns (uint256)` [external] — line 465
- `sell(uint256,uint256) returns (uint256)` [external] — line 499
- `setHalfLife(uint64) onlyOperatorOrManager beforeDeadline` [external] — line 918
- `setLocalReserveFeeBps(uint256) onlyOperator` [external] — line 947
- `setManager(address) onlyOperatorOrManager` [external] — line 965
- `setMaxBorrowDeltaBps(uint16) onlyOperatorOrManager beforeDeadline` [external] — line 941
- `setPendingOperator(address) onlyOperator` [external] — line 954
- `setRedeemFeeBps(uint16) onlyOperatorOrManager beforeDeadline` [external] — line 934
- `setTargetFreeDebtRatio(uint16,uint16) onlyOperatorOrManager beforeDeadline` [external] — line 925
- `writeOff(address,address) returns (bool)` [external] — line 421
- `accrueInterest()` [public] — line 196
- `adjust(address,int256,int256)` [public] — line 241
- `collateralToInternal(uint256) returns (uint256)` [public] — line 855
- `constructor(Lender.LenderParams)` [public] — line 124
- `getBuyAmountOut(uint256) returns (uint256, uint256)` [public] — line 816
- `getBuyFeeBps() returns (uint256)` [public] — line 790
- `getCollateralPrice() returns (uint256, bool, bool)` [public] — line 715
- `getDebtOf(address) returns (uint256)` [public] — line 703
- `getFreeDebtRatio() returns (uint256)` [public] — line 698
- `getRedeemAmountOut(uint256) returns (uint256)` [public] — line 765
- `getSellAmountOut(uint256) returns (uint256)` [public] — line 774
- `internalToCollateral(uint256) returns (uint256)` [public] — line 868
- `setRedemptionStatus(address,bool)` [public] — line 338

### Lens (contract)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Lens.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `getCollateralOf(Lender,address) returns (uint256)` [public] — line 11
- `getDebtOf(Lender,address) returns (uint256)` [public] — line 43

### ILender (interface)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Vault.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `accrueInterest()` [external] — line 7
- `coin() returns (ERC20)` [external] — line 8
- `getPendingInterest() returns (uint256)` [external] — line 9

### Vault (contract)
- file: `/home/shinobi/Desktop/web3/hunting/2025-12-Monolith/2025-12-monolith-stablecoin-factory-Kode-n-Rolla/Monolith/src/Vault.sol`
- receive(): ❌
- fallback(): ❌

**Functions**
- `DOMAIN_SEPARATOR() returns (bytes32)` [public] — line 162
- `approve(address,uint256) returns (bool)` [public] — line 68
- `constructor(string,string,address)` [public] — line 22
- `convertToAssets(uint256) returns (uint256)` [public] — line 130
- `convertToShares(uint256) returns (uint256)` [public] — line 124
- `deposit(uint256,address) returns (uint256)` [public] — line 46
- `deposit(uint256,address) accrueInterest returns (uint256)` [public] — line 47
- `maxDeposit(address) returns (uint256)` [public] — line 160
- `maxMint(address) returns (uint256)` [public] — line 164
- `maxRedeem(address) returns (uint256)` [public] — line 172
- `maxWithdraw(address) returns (uint256)` [public] — line 168
- `mint(uint256,address) returns (uint256)` [public] — line 60
- `mint(uint256,address) accrueInterest returns (uint256)` [public] — line 75
- `permit(address,address,uint256,uint256,uint8,bytes32,bytes32)` [public] — line 116
- `previewDeposit(uint256) returns (uint256)` [public] — line 136
- `previewDeposit(uint256) returns (uint256)` [public] — line 125
- `previewMint(uint256) returns (uint256)` [public] — line 140
- `previewMint(uint256) returns (uint256)` [public] — line 139
- `previewRedeem(uint256) returns (uint256)` [public] — line 152
- `previewWithdraw(uint256) returns (uint256)` [public] — line 146
- `redeem(uint256,address,address) returns (uint256)` [public] — line 95
- `redeem(uint256,address,address) accrueInterest returns (uint256)` [public] — line 114
- `totalAssets() returns (uint256)` [public] — line 122
- `totalAssets() returns (uint256)` [public] — line 39
- `transfer(address,uint256) returns (bool)` [public] — line 76
- `transferFrom(address,address,uint256) returns (bool)` [public] — line 90
- `withdraw(uint256,address,address) returns (uint256)` [public] — line 73
- `withdraw(uint256,address,address) accrueInterest returns (uint256)` [public] — line 101

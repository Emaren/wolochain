package app_test

import (
	"bytes"
	"encoding/json"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"cosmossdk.io/log"
	sdkmath "cosmossdk.io/math"
	abci "github.com/cometbft/cometbft/abci/types"
	cdb "github.com/cometbft/cometbft-db"
	cfg "github.com/cometbft/cometbft/config"
	clog "github.com/cometbft/cometbft/libs/log"
	"github.com/cometbft/cometbft/node"
	"github.com/cometbft/cometbft/p2p"
	"github.com/cometbft/cometbft/privval"
	"github.com/cometbft/cometbft/proxy"
	sm "github.com/cometbft/cometbft/state"
	bs "github.com/cometbft/cometbft/store"
	ct "github.com/cometbft/cometbft/types"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	dbm "github.com/cosmos/cosmos-db"
	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/client/flags"
	"github.com/cosmos/cosmos-sdk/server"
	"github.com/cosmos/cosmos-sdk/crypto/keys/secp256k1"
	sim "github.com/cosmos/cosmos-sdk/testutil/sims"
	sdk "github.com/cosmos/cosmos-sdk/types"
	auth "github.com/cosmos/cosmos-sdk/x/auth/types"
	bank "github.com/cosmos/cosmos-sdk/x/bank/types"
	"github.com/emaren/wolochain/app"
	"github.com/spf13/viper"
	"github.com/stretchr/testify/require"
)

// Test-only chain: never accepts a production home or validator identity.
const c06Chain = "c06-disposable-recovery"

func c06App(t *testing.T, home string) *app.App {
	t.Helper()
	db, err := dbm.NewDB("application", dbm.GoLevelDBBackend, filepath.Join(home, "data"))
	require.NoError(t, err)
	opt := viper.New()
	opt.Set(flags.FlagHome, home)
	return app.New(log.NewNopLogger(), db, nil, true, opt, baseapp.SetChainID(c06Chain))
}

func TestC06CheckpointChild(t *testing.T) {
	home := os.Getenv("C06_SYNTHETIC_HOME")
	if home == "" {
		t.Skip("child only")
	}
	require.Equal(t, "c06-synthetic-node", filepath.Base(home))
	require.NoError(t, os.Mkdir(home, 0700))
	cfg.EnsureRoot(home)
	conf := cfg.DefaultConfig().SetRoot(home)
	conf.DBBackend = "goleveldb"
	conf.RPC.ListenAddress = ""
	conf.P2P.ListenAddress = "tcp://127.0.0.1:0"
	conf.P2P.PexReactor = false
	conf.P2P.Seeds = ""
	conf.P2P.PersistentPeers = ""
	conf.Instrumentation.Prometheus = false
	conf.Consensus.TimeoutCommit = 2 * time.Second
	conf.TxIndex.Indexer = "null"
	pv := privval.GenFilePV(conf.PrivValidatorKeyFile(), conf.PrivValidatorStateFile())
	pv.Save()
	pub, err := pv.GetPubKey()
	require.NoError(t, err)
	vals := ct.NewValidatorSet([]*ct.Validator{ct.NewValidator(pub, 1)})
	a := c06App(t, home)
	k := secp256k1.GenPrivKey()
	address := sdk.AccAddress(k.PubKey().Address())
	account := auth.NewBaseAccount(address, k.PubKey(), 0, 0)
	state, err := sim.GenesisStateWithValSet(a.AppCodec(), a.DefaultGenesis(), vals,
		[]auth.GenesisAccount{account}, bank.Balance{Address: address.String(),
			Coins: sdk.NewCoins(sdk.NewCoin("uwolo", sdkmath.NewInt(1000000000)))})
	require.NoError(t, err)
	raw, err := json.Marshal(state)
	require.NoError(t, err)
	gen := &ct.GenesisDoc{ChainID: c06Chain, InitialHeight: 1,
		GenesisTime: time.Now().Add(-time.Second), ConsensusParams: ct.DefaultConsensusParams(),
		Validators: []ct.GenesisValidator{{Address: pub.Address(), PubKey: pub, Power: 1}}, AppState: raw}
	require.NoError(t, gen.ValidateAndComplete())
	require.NoError(t, gen.SaveAs(conf.GenesisFile()))
	key, err := p2p.LoadOrGenNodeKey(conf.NodeKeyFile())
	require.NoError(t, err)
	n, err := node.NewNode(conf, pv, key, proxy.NewLocalClientCreator(server.NewCometABCIWrapper(a)),
		node.DefaultGenesisDocProviderFunc(conf), cfg.DefaultDBProvider,
		node.DefaultMetricsProvider(conf.Instrumentation), clog.NewNopLogger())
	require.NoError(t, err)
	require.NoError(t, n.Start())
	stopped := false
	defer func() { if !stopped { _ = n.Stop() } }()
	deadline := time.Now().Add(35*time.Second)
	for n.BlockStore().Height() < 3 && time.Now().Before(deadline) {
		time.Sleep(50*time.Millisecond)
	}
	require.GreaterOrEqual(t, n.BlockStore().Height(), int64(3))
	// Allow the current commit to finish; next commit has a 2s delay.
	time.Sleep(250*time.Millisecond)
	require.NoError(t, n.Stop())
	stopped = true
	require.NoError(t, a.Close())
	// Parent only copies data once this subprocess has exited.
	require.NoError(t, os.WriteFile(filepath.Join(home,"fixture-account"), []byte(address.String()),0600))
}

type c06Witness struct {
	Height int64
	AppHash, BlockHash, Balance, Supply string
}

func c06Read(t *testing.T, home, address string) c06Witness {
	t.Helper()
	dir := filepath.Join(home,"data")
	blockDB, err := cdb.NewDB("blockstore", cdb.GoLevelDBBackend,dir)
	require.NoError(t,err)
	blocks := bs.NewBlockStore(blockDB)
	defer func(){require.NoError(t,blocks.Close())}()
	stateDB,err := cdb.NewDB("state",cdb.GoLevelDBBackend,dir)
	require.NoError(t,err)
	store := sm.NewStore(stateDB,sm.StoreOptions{})
	defer func(){require.NoError(t,store.Close())}()
	s,err := store.Load()
	require.NoError(t,err)
	a:=c06App(t,home)
	defer func(){require.NoError(t,a.Close())}()
	info,err:=a.Info(&abci.RequestInfo{})
	require.NoError(t,err)
	require.Equal(t,c06Chain,s.ChainID)
	require.GreaterOrEqual(t,s.LastBlockHeight,int64(3))
	require.Equal(t,s.LastBlockHeight,blocks.Height())
	require.Equal(t,s.LastBlockHeight,info.LastBlockHeight)
	require.NotEmpty(t,s.AppHash)
	require.True(t,bytes.Equal(s.AppHash,info.LastBlockAppHash))
	b:=blocks.LoadBlock(blocks.Height())
	require.NotNil(t,b)
	require.Equal(t,s.LastBlockID.Hash,b.Hash())
	addr,err:=sdk.AccAddressFromBech32(address)
	require.NoError(t,err)
	ctx:=a.NewUncachedContext(false,cmtproto.Header{Height:s.LastBlockHeight})
	balance:=a.BankKeeper.GetAllBalances(ctx,addr).String()
	supply:=a.BankKeeper.GetSupply(ctx,"uwolo").String()
	require.NotEmpty(t,balance)
	require.NotEmpty(t,supply)
	return c06Witness{s.LastBlockHeight,string(s.AppHash),string(b.Hash()),balance,supply}
}

func c06Copy(t *testing.T, src,dst string) {
	t.Helper()
	require.NoError(t,filepath.WalkDir(src,func(path string,d fs.DirEntry,err error) error {
		if err!=nil{return err}
		rel,err:=filepath.Rel(src,path);if err!=nil{return err}
		target:=filepath.Join(dst,rel)
		info,err:=d.Info();if err!=nil{return err}
		if d.IsDir(){return os.Mkdir(target,0700)}
		if !info.Mode().IsRegular(){return fs.ErrInvalid}
		in,err:=os.Open(path);if err!=nil{return err};defer in.Close()
		out,err:=os.OpenFile(target,os.O_CREATE|os.O_EXCL|os.O_WRONLY,0600);if err!=nil{return err}
		_,e:=io.Copy(out,in);closeErr:=out.Close();if e!=nil{return e};return closeErr
	}))
}

func TestC06PhysicalCometSDKLevelDBRecovery(t *testing.T) {
	root:=t.TempDir()
	home:=filepath.Join(root,"c06-synthetic-node")
	exe,err:=os.Executable();require.NoError(t,err)
	child:=exec.Command(exe,"-test.run=^TestC06CheckpointChild$","-test.v")
	child.Env=append(os.Environ(),"C06_SYNTHETIC_HOME="+home)
	out,err:=child.CombinedOutput()
	require.NoError(t,err,"%s",out)
	address,err:=os.ReadFile(filepath.Join(home,"fixture-account"));require.NoError(t,err)
	restored:=filepath.Join(root,"restored")
	require.NoError(t,os.Mkdir(restored,0700))
	// Actual closed CometBFT stores + SDK IAVL application database. No
	// validator/node key/config copied and no restored consensus process started.
	c06Copy(t,filepath.Join(home,"data"),filepath.Join(restored,"data"))
	_,err=os.Stat(filepath.Join(restored,"config","priv_validator_key.json"))
	require.True(t,os.IsNotExist(err))
	before:=c06Read(t,home,string(address))
	after:=c06Read(t,restored,string(address))
	require.Equal(t,before,after)
	t.Logf("C06 synthetic Comet/SDK LevelDB parity height=%d app_hash=%x block_hash=%x balance=%s supply=%s",after.Height,after.AppHash,after.BlockHash,after.Balance,after.Supply)
}
